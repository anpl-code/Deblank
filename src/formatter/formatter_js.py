import tempfile
import logging
import os
import re
import subprocess
from operator import itemgetter
from tree_sitter_languages import get_parser
import json

from .base import BaseFormatter
from .utils import close_open_brackets,remove_appended_brackets,mask_protected_nodes,restore_protected_nodes

SUFFIX_MAP={
    'javascript':'.js',
    'typescript': '.ts',
    'tsx':'.tsx'
}

INDENT_LEVEL=2

class JSFormatter(BaseFormatter):
    prereq=None
    @classmethod
    def check_prereq(cls) -> bool:
        if(cls.prereq is not None):
            return cls.prereq
        result = subprocess.run(
            ["npm", "list", "--depth=0", "--json"],
            capture_output=True,
            text=True,
            check=True
        )
        installed = json.loads(result.stdout)
        dependencies = installed.get("dependencies", {})
        if("@babel/parser" in dependencies and "@babel/generator" in dependencies):
            logging.debug("Babel is installed.")
            cls.prereq=True
        else:
            logging.error("Babel is not installed.")
            cls.prereq=False
        return cls.prereq

    def __init__(self):
        self.lang='javascript'
        self.unformatted_config="config/eslint_js_unformat.config.mjs"
        self.formatted_config="config/eslint_js_format.config.mjs"

        self.indent_nodes=['class_body','switch_body','statement_block']

        self.string_types=['string','template_string']
        self.quotes=['\'','"','`']
        self.multiline_quotes_start=['`']

    def format_code(self,code:str,repair_strategy:str,info:dict) -> str:
        formatted_code,err_msg=self._run_babel(code,'format')
        if(formatted_code!="<Error>"):
            info.update({"status":"success","repair_attempted":False,"original_error":None})
            return formatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            former,remain=self.cut_incomplete_statements(code)
            former=self.close_open_string(former)
            appended_code,appended_len=close_open_brackets(former,lang=self.lang)
            formatted_code,err_msg=self._run_babel(appended_code,'format')
            if(formatted_code=="<Error>"):
                info['status']='failed'
                return None
            formatted_code=remove_appended_brackets(formatted_code,appended_len,ignore_elems=[';'])
            if(remain):
                initial_indent=0
                for line in reversed(formatted_code.splitlines()):
                    if(line.strip()):
                        initial_indent=len(line)-len(line.lstrip())
                        break
                remain=self.format_code_re(remain,initial_indent=initial_indent)
            formatted_code=formatted_code.rstrip()+"\n"+remain
            info['status']='success'
            return formatted_code
        else:
            logging.error(f"Unknown repair strategy: {repair_strategy}")
            raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")
    
    def unformat_code(self,code:str,repair_strategy:str,info:dict) -> str:
        unformatted_code,err_msg=self._run_babel(code,'unformat')
        if(unformatted_code!="<Error>"):
            info.update({"status":"success","repair_attempted":False,"original_error":None})
            return unformatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            former,remain=self.cut_incomplete_statements(code)
            last_char=former[-1]
            former=self.close_open_string(former)
            appended_code,appended_len=close_open_brackets(former,lang=self.lang)
            unformatted_code,err_msg=self._run_babel(appended_code,'unformat')
            if(unformatted_code=='<Error>'):
                info['status']='failed'
                return None
            unformatted_code=remove_appended_brackets(unformatted_code,appended_len,ignore_elems=[';']).rstrip()# TODO: babel may add or remove brackets
            if(remain):
                remain=self.unformat_code_re(remain)
                if(unformatted_code and unformatted_code[-1] not in ['\n','{','}',';']):
                    unformatted_code+='\n'
            unformatted_code+=remain
            info['status']='success'
            return unformatted_code
        else:
            logging.error(f"Unknown repair strategy: {repair_strategy}")
            raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")

    def _run_babel(self,code:str,option):
        suffix=SUFFIX_MAP.get(self.lang.lower(),'')
        try:
            with tempfile.NamedTemporaryFile(mode='w+', suffix=suffix, delete=False,dir='./temp') as temp_in:
                temp_in.write(code)
                temp_in_path = temp_in.name
                logging.debug(f"Temporarily enter the file path: {temp_in_path}")

            temp_out_path = temp_in_path + '.out'
            cmd = ['node','src/formatter/babel.js',option,self.lang,temp_in_path,temp_out_path]
            logging.debug(f"Run commands: {' '.join(cmd)}")
                    
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
            logging.debug(f"Babel Return code: {result.returncode}")
            logging.debug(f"Babel Standard output: {result.stdout}")
            logging.debug(f"Babel Error output: {result.stderr}")

            if result.stderr:
                logging.debug(f"Babel error: {result.stderr}")
                os.unlink(temp_in_path)
                return "<Error>",result.stderr

            with open(temp_out_path, 'r') as f:
                processed_code = f.read()
                logging.debug("The formatted code was successfully read")
                    
            os.unlink(temp_in_path)
            os.unlink(temp_out_path)
            logging.debug("Temporary file deleted")

            return processed_code, None

        except Exception as e:
            logging.error(f"Error in Babel processing: {e}")
            os.unlink(temp_in_path)
            if(os.path.exists(temp_out_path)):
                os.unlink(temp_out_path)
            return "<Error>", str(e)
    
    def unformat_code_re(self,code:str,info:dict=None):
        if(info is not None):
            info['status']='regex'
        code=self.concat_lines(code)
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed=re.sub(r'[ \t]+',' ',masked_code)
        compressed = re.sub(r'\n+', '\n', compressed)#auto semicolon
        compressed = re.sub(r'\s+;', ';', compressed)
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'[ \t]+([,\(\)\{])', r'\1', compressed)
        compressed = re.sub(r'\s+\}','}', compressed)
        compressed = re.sub(r'([,\(\)\}])[ \t]+', r'\1', compressed)
        compressed = re.sub(r'\{\s+','{',compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#spaces at line start
        compressed = re.sub(r'(_LC>>)\s+',r'\1',compressed)
        compressed = re.sub(r'[ \t]+\n','\n',compressed)#spaces at line end
        automatic_semi_ops=r'`|,|:|;|\*|%|>|<|=|\[|\(|\?|\^|\||&|/'
        compressed = re.sub(r'\s+(['+automatic_semi_ops+r'])(?!<PROTECTED)',r'\1',compressed)
        compressed = re.sub(r'[ \t]+([~!])',r'\1',compressed)
        compressed = re.sub(r'([*/=\?:&%^|<>~!]+)[ \t]+',r'\1',compressed)
        compressed = re.sub(r'(?<!-|\+)[ \t]+([-+])',r'\1',compressed)
        compressed = re.sub(r'([-+])[ \t]+(?!-|\+)',r'\1',compressed)
        restored_code=restore_protected_nodes(compressed,segments)
        return restored_code.strip()

    def format_code_re(self,code:str,info=None,initial_indent=0):
        if(info is not None):
            info['status']='regex'
        parser=get_parser(self.lang)
        #add newlines
        edits=list()
        tree=parser.parse(bytes(code,'utf8'))
        def traverse(node):
            if(node.type in self.indent_nodes):
                for child in node.children:
                    if child.type == '{':
                        edits.append((child.end_byte, '\n'))
                    elif child.type == '}':
                        edits.append((child.start_byte, '\n'))
                        edits.append((child.end_byte, '\n'))
            elif(node.type in ['switch_case','switch_default']):
                for child in node.children:
                    if child.type==':':
                        edits.append((child.end_byte, '\n'))
            elif(node.type==';'):
                if(node.parent.type!='for_statement'):
                    edits.append((node.end_byte,'\n'))
            for child in node.children:
                traverse(child)
        traverse(tree.root_node)
        edits.sort(key=lambda x:x[0],reverse=True)
        byte_code = bytes(code, "utf8")
        last_pos = len(byte_code)
        parts = []
        for pos,insert_str in edits:
            parts.append(byte_code[pos:last_pos].decode("utf8"))
            parts.append(insert_str)
            last_pos = pos
        parts.append(byte_code[0:last_pos].decode("utf8"))
        code="".join(reversed(parts))

        #apply indentation
        tree=parser.parse(bytes(code,'utf8'))
        lines=code.splitlines()
        formatted_lines=list()
        byte_offset=0
        prev_indent=initial_indent
        for line in lines:
            if(not line.strip()):
                if(formatted_lines[-1].endswith("}")):
                    formatted_lines.append("")
                byte_offset+=len(line.encode('utf8'))+1
                continue
            node=tree.root_node.descendant_for_byte_range(byte_offset,byte_offset+1)
            indent=initial_indent
            parent=node
            while parent:
                if(parent.parent==parent):
                    logging.debug("Infinite loop detected.")
                    indent=prev_indent
                    break
                if(parent.type in self.indent_nodes):
                    indent+=INDENT_LEVEL
                parent=parent.parent

            if(line.startswith("}")):
                indent=max(0,indent-INDENT_LEVEL)
            if(line.startswith("case ") or line.startswith("default:")):
                indent=max(0,indent-INDENT_LEVEL)

            formatted_lines.append(" "*indent+line.strip())

            byte_offset=byte_offset+len(line.encode('utf8'))+1
            prev_indent=indent
        return "\n".join(formatted_lines)
    
    def cut_incomplete_statements(self,code:str) -> str:
        masked_code,segments=mask_protected_nodes(code,self.lang)
        end_markers=[';', '}','{']
        last_pos=-1
        for marker in end_markers:
            pos=masked_code.rfind(marker)
            if(pos!=-1):
                pos+=len(marker) - 1 #include the marker
                if (pos>last_pos):
                    last_pos=pos
        if(last_pos==-1):
            former=masked_code
            remain=""
        else:
            former=masked_code[:last_pos+1]
            remain=masked_code[last_pos+1:]
        former=restore_protected_nodes(former,segments)
        remain=restore_protected_nodes(remain,segments)
        return former,remain.strip()
    
    def concat_lines(self,code):
        code=re.sub(r'\\\n','',code)
        return code
    
    def close_open_string(self,code:str):
        code=self._fill_missing_quotes_by_tree_sitter(code)
        
        masked_code,segments=mask_protected_nodes(code,self.lang)
        code_lines=masked_code.splitlines(keepends=True)

        #merge \\n
        merged_lines=list()
        for line in code_lines:
            if(merged_lines and merged_lines[-1].rstrip().endswith('\\')):
                merged_lines[-1]+=line
            else:
                merged_lines.append(line)
        
        new_lines=list()
        for line_no,line in enumerate(merged_lines):
            skip=False
            for quote in self.multiline_quotes_start:
                if(quote in line):
                    skip=True
                    break
            if(skip):
                new_lines.extend(merged_lines[line_no:])
                break

            cur_quote=None
            is_escaped=False
            new_line=""
            last_idx=0
            for idx,char in enumerate(line):
                if is_escaped:
                    is_escaped=False
                    continue
                if char=='\\':
                    is_escaped=True
                    continue

                if(cur_quote and char==cur_quote):
                    cur_quote=None
                elif(not cur_quote and char in self.quotes):
                    cur_quote=char
                if char in ['{','}',';','\n',')',']'] and cur_quote:#is_escaped will skip \\n
                    new_line+=line[last_idx:idx]+cur_quote
                    cur_quote=None
                    last_idx=idx
            new_line+=line[last_idx:]
            if(cur_quote):
                new_line=new_line.rstrip()+cur_quote+"\n"
            new_lines.append(new_line)
        restored_code=restore_protected_nodes("".join(new_lines),segments)
        return restored_code


    def _fill_missing_quotes_by_tree_sitter(self,code):
        parser=get_parser(self.lang)
        byte_code=bytearray(code,'utf8')
        tree=parser.parse(byte_code)
        edits=list()
        def find_missing(node):
            for child in node.children:
                if(child.is_missing and (
                    (child.type in self.quotes and node.type in self.string_types) or
                    (child.type=='/' and node.type=='regex') or
                    (child.type==';')
                )):
                    edits.append((child.start_byte,child.type))
                else:
                    find_missing(child)
        find_missing(tree.root_node)
        edits=sorted(edits,key=lambda x: x[0],reverse=True)
        for pos, quote in edits:
            byte_code[pos:pos] = quote.encode('utf8')
        return byte_code.decode('utf8')
    
class TSFormatter(JSFormatter):
    def __init__(self):
        super().__init__()
        self.lang='typescript'
        self.unformatted_config="config/eslint_ts_unformat.config.mjs"
        self.formatted_config="config/eslint_ts_format.config.mjs"

        self.indent_nodes=['class_body','switch_body','statement_block','interface_body']

        self.string_types=['string','template_string','template_literal_type']

class TSXFormatter(JSFormatter):
    def __init__(self):
        super().__init__()
        self.lang='tsx'

        self.indent_nodes=['class_body','switch_body','statement_block','interface_body']

        self.string_types=['string','template_string','template_literal_type']