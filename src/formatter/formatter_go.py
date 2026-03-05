import subprocess
import tempfile
import logging
import os
import re
from tree_sitter_languages import get_parser
import shutil

from .base import BaseFormatter
from .utils import mask_protected_nodes,restore_protected_nodes,RepairUnableError,close_open_brackets,remove_appended_brackets

GO_FEATURES=[
            (re.compile(r'^\s*package\s+\w+',re.MULTILINE),2), #start by package declaration
            (re.compile(r'import\s*\(',re.MULTILINE),2),
            (re.compile(r'func\s+\w+(?:\[[^\]]*\])?\s*\([^)]*\)\s*(?:\([^)]*\)|[^{\n]+)?\s*\{',re.MULTILINE),2), #function signature with return value
            (re.compile(r':='),1),
            (re.compile(r'\b(defer|chan|go\s+func|fallthrough)\b'),2),
            (re.compile(r'err\s*!=\s*nil'),2),
            (re.compile(r'\b(select)\b|interface\s*{'),1)
] 

INDENT_LEVEL=1

class GoFormatter(BaseFormatter):
    prereq=None
    @classmethod
    def check_prereq(cls) -> bool:
        if(cls.prereq is not None):
            return cls.prereq
        if(shutil.which("go")):
            logging.debug("Go is installed.")
            cls.prereq=True
        else:
            logging.error("Go is not installed.")
            cls.prereq=False
        return cls.prereq
    
    def __init__(self):
        super().__init__()
        self.lang='go'

        self.indent_nodes=['block', 'field_declaration_list', 'interface_type',
                           'expression_switch_statement', 'type_switch_statement','select_statement',
                           'var_spec_list','import_spec_list']

    def unformat_code(self,code:str,repair_strategy:str,info:dict) -> str:
        if(not info['language_info']):#language not specified
            if(not self._go_heuristics(code)):
                info.update({"status":"failed","repair_attempted":False,
                             "original_error":"Input does not appear to be Go source code."})
                return None
        unformatted_code,err_msg=self._run_scanner(code)
        if(unformatted_code!="<Error>"):
            info.update({"status":"success","repair_attempted":False,"original_error":err_msg if err_msg else None})
            return unformatted_code
        else:
            info.update({"status":"failed","repair_attempted":False,"original_error":err_msg})
          

    def _run_scanner(self,code):
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False,dir='./temp') as temp_in:
                    temp_in.write(code)
                    temp_in_path = temp_in.name
                    logging.debug(f"Temporarily enter the file path: {temp_in_path}")

            temp_out_path=temp_in_path+".out"
            cmd=['go','run','src/formatter/go/unformat.go',temp_in_path]
            logging.debug(f"Run commands: {' '.join(cmd)}")
                    
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
            logging.debug(f"Go scanner Return code: {result.returncode}")
            logging.debug(f"Go scanner Standard output: {result.stdout}")
            logging.debug(f"Go scanner Error output: {result.stderr}")

            if result.stderr:
                logging.debug(f"Go scanner error: {result.stderr}")
                os.unlink(temp_in_path)
                return "<Error>",result.stderr

            with open(temp_out_path, 'r') as f:
                processed_code = f.read()
                logging.debug("The formatted code was successfully read")
                    
            os.unlink(temp_in_path)
            os.unlink(temp_out_path)
            logging.debug("Temporary file deleted")

            return processed_code, result.stdout

        except Exception as e:
            logging.error(f"Error in Go scanner processing: {e}")
            os.unlink(temp_in_path)
            if(os.path.exists(temp_out_path)):
                os.unlink(temp_out_path)
            return "<Error>", str(e)
     
    def _go_heuristics(self,code:str):
        #remove comments
        re_line_comment=re.compile(r'//.*')
        re_block_comment=re.compile(r'/\*[\s\S]*?\*/')
        code=re_line_comment.sub('',code)
        code=re_block_comment.sub('',code)

        score=0
        for feature,sc in GO_FEATURES:
            if(feature.search(code)):
                score+=sc
        return score>=3
    
    def unformat_code_re(self,code:str,info=None):
        if(info is not None):
            info['status']='regex'
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed = re.sub(r'[ \t]+',' ',masked_code)
        compressed = re.sub(r'\s+;', ';', compressed)
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'\n+', '\n', compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#space at line start
        compressed = re.sub(r'(_LC>>)\s+',r'\1',compressed)
        compressed = re.sub(r'[ \t]+\n','\n',compressed)#space at line end
        
        compressed = re.sub(r'[ \t]+([,\(\{\[\.\]])',r'\1',compressed)
        compressed = re.sub(r'\s+([\)\}])',r'\1', compressed)
        compressed = re.sub(r'([,\)\}\]\.])[ \t]+', r'\1', compressed)
        compressed = re.sub(r'([\{\[\(])\s+',r'\1',compressed)
        
        compressed = re.sub(r'[ \t]+([\*/%&|\^>=!:]+)',r'\1',compressed)
        compressed = re.sub(r'[ \t]+(?=<(?!<PROTECTED))', '', compressed)
        compressed = re.sub(r'([\*/%&|\^<=!:]+)\s+',r'\1',compressed)
        compressed = re.sub(r'(?<!PLACEHOLDER>)>\s+', '>',compressed)
        compressed = re.sub(r'(?<!-|\+)[ \t]+([-+])',r'\1',compressed)
        compressed = re.sub(r'([-+])[ \t]+(?!-|\+)',r'\1',compressed)
        restored_code=restore_protected_nodes(compressed,segments)
        return restored_code.strip()
    
    def format_code(self,code:str,repair_strategy:str,info:dict) -> str:
        formatted_code,err_msg=self._run_gofmt(code)
        if(formatted_code!="<Error>"):
            info.update({"status":"success","repair_attempted":False,"original_error":None})
            return formatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        if(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            try:
                code,repair_info=self.repair_syntax_error(code,err_msg)
                former,remain=self.cut_incomplete_statement(code)
                appended_code,appended_len=close_open_brackets(former,lang=self.lang)
                formatted_code,err_msg=self._run_gofmt(appended_code)
                if(formatted_code=='<Error>'):
                    info['status']='failed'
                    return None
                if(repair_info['added_package_declaration']):
                    formatted_code=formatted_code.replace("package main","").lstrip()
                formatted_code=remove_appended_brackets(formatted_code,appended_len,ignore_elems=[';'])
                if(remain):
                    # the last non-empty line's indent
                    initial_indent=0
                    for line in reversed(formatted_code.splitlines()):
                        if(line.strip()):
                            initial_indent=len(line)-len(line.lstrip())
                            if(line.rstrip().endswith("{")):
                                initial_indent+=INDENT_LEVEL
                            break
                    remain=self.format_code_re(remain,initial_indent=initial_indent)
                    formatted_code=formatted_code.rstrip()+"\n"+remain
                info['status']='success'
                return formatted_code
            except RepairUnableError:
                info['status']='failed'
                return None
        
    def _run_gofmt(self,code):
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False,dir='./temp') as temp_in:
                    temp_in.write(code)
                    temp_in_path = temp_in.name
                    logging.debug(f"Temporarily enter the file path: {temp_in_path}")
                    
            cmd=['gofmt','-e','-w',temp_in_path]
            logging.debug(f"Run commands: {' '.join(cmd)}")
                    
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
            logging.debug(f"Gofmt Return code: {result.returncode}")
            logging.debug(f"Gofmt Standard output: {result.stdout}")
            logging.debug(f"Gofmt Error output: {result.stderr}")

            if result.stderr:
                logging.debug(f"Gofmt error: {result.stderr}")
                os.unlink(temp_in_path)
                return "<Error>",result.stderr

            with open(temp_in_path, 'r') as f:
                processed_code = f.read()
                logging.debug("The formatted code was successfully read")
                    
            os.unlink(temp_in_path)
            logging.debug("Temporary file deleted")

            return processed_code, None

        except Exception as e:
            logging.error(f"Error in Go scanner processing: {e}")
            os.unlink(temp_in_path)
            return "<Error>", str(e)

    def repair_syntax_error(self,code,err_msg):
        code_lines=code.splitlines()
        msgs=err_msg.splitlines()
        repair_info={"added_package_declaration":False}
        package_pattern=re.compile(r'^(.+?):1:(\d+):\s+expected \'package\'')
        str_pattern=re.compile(r'(.+?):(\d+):(\d+):\s+string literal not terminated\b')
        for msg in msgs:
            if(package_pattern.match(msg)):
                repair_info['added_package_declaration']=True
                code_lines[0]="package main\n"+code_lines[0]
            elif(m:=str_pattern.match(msg)):
                line_num=int(m.group(2))-1
                new_line=code_lines[line_num]
                idx=len(new_line)-1
                while idx>=0:
                    if new_line[idx] not in [';',']','{','}',')']:
                        break
                    idx-=1
                code_lines[line_num]=new_line[:idx+1]+'"'+new_line[idx+1:]
        return "\n".join(code_lines),repair_info

    def cut_incomplete_statement(self,code):
        try:
            with tempfile.NamedTemporaryFile(mode='w+', delete=False,dir='./temp') as temp_in:
                temp_in.write(code)
                temp_in_path = temp_in.name
                logging.debug(f"Temporarily enter the file path: {temp_in_path}")
            former_path=temp_in_path+".former.out"
            remain_path=temp_in_path+".remain.out"
                    
            cmd=['go','run','src/formatter/go/cut_incomplete_statement.go',temp_in_path]
            logging.debug(f"Run commands: {' '.join(cmd)}")
                    
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
            logging.debug(f"Go program Return code: {result.returncode}")
            logging.debug(f"Go program Standard output: {result.stdout}")
            logging.debug(f"Go program Error output: {result.stderr}")

            if result.stderr:
                logging.debug(f"Go program error: {result.stderr}")
                os.unlink(temp_in_path)
                if(os.path.exists(former_path)):
                    os.unlink(former_path)
                if(os.path.exists(remain_path)):
                    os.unlink(remain_path)
                raise RepairUnableError

            with open(former_path, 'r') as f1, open(remain_path,'r') as f2:
                former=f1.read()
                remain=f2.read()
                logging.debug("The truncated code was successfully read")
                    
            os.unlink(temp_in_path)
            os.unlink(former_path)
            os.unlink(remain_path)
            logging.debug("Temporary file deleted")

            return former,remain

        except Exception as e:
            if(isinstance(e,RepairUnableError)):
                raise e
            logging.error(f"Error in Go program processing: {e}")
            if(os.path.exists(former_path)):
                os.unlink(former_path)
            if(os.path.exists(remain_path)):
                os.unlink(remain_path)
            raise RepairUnableError
    
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
                    if child.type == '{' or child.type == '(':
                        edits.append((child.end_byte, '\n'))
                    elif child.type == '}' or child.type == ')':
                        edits.append((child.start_byte, '\n'))
            elif(node.type==';'):
                if(node.parent.type in ['if_statement','type_switch_statement','expression_switch_statement']):
                    edits.append((node.end_byte,' '))
                elif(node.parent.type!='for_clause'):
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

            formatted_lines.append("\t"*indent+line.strip())

            byte_offset=byte_offset+len(line.encode('utf8'))+1
            prev_indent=indent
        return "\n".join(formatted_lines)