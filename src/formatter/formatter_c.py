import subprocess
import os
import logging
import re
import shutil

from .base import BaseFormatter
from .utils import *
from .io_utils import create_temp_input_file, read_text_file, safe_cleanup, normalize_stderr

CONFIG_PATH={
    'cpp':['config/cpp_formatted.cfg','config/cpp_unformatted.cfg'],
    'c_sharp':['config/csharp_formatted.cfg','config/csharp_unformatted.cfg'],
    'java':['config/java_formatted.cfg','config/java_unformatted.cfg'],
    'c':['config/c_formatted.cfg','config/c_unformatted.cfg']
}

SUFFIX_MAP={
    'cpp':'.cpp',
    'c_sharp':'.cs',
    'java':'.java',
    'c':".c"
}

class CFamilyFormatter(BaseFormatter):#formatter for C family
    prereq=None
    @classmethod
    def check_prereq(cls) -> bool:
        if(cls.prereq is not None):
            return cls.prereq
        if(shutil.which("uncrustify")):
            logging.debug("Uncrustify is installed.")
            cls.prereq=True
        else:
            logging.error("Uncrustify is not installed.")
            cls.prereq=False
        return cls.prereq
    
    def remove_align_space(self,code):
        code=re.sub(r'(?<=\S)[ \t]+(?=//|/\*)',' ',code)
        return code
    
    def cut_long_line(self,code:str):
        code,segments=mask_protected_nodes(code,self.lang)
        code=re.sub(r'([;\}\{])',r'\1\n',code)
        for plh,content in segments.items():
            if(content.startswith("/*") and content.endswith("*/")):#block comment
                segments[plh]=content+"\n"
        restored_code=restore_protected_nodes(code,segments)
        return restored_code

    def _run_uncrustify(self,code:str,config_file:str):
        suffix=SUFFIX_MAP.get(self.lang.lower(),'')
        temp_in_path=None
        temp_out_path=None
        try:
            temp_in_path = create_temp_input_file(code, suffix=suffix)
            logging.debug(f"Temporary input file path: {temp_in_path}")
                    
            temp_out_path = temp_in_path + '.out'
            logging.debug(f"Temporary output file path: {temp_out_path}")

            logging.debug(f"The path of the configuration file used: {config_file}")
            if not os.path.exists(config_file):
                err_msg=f"Configuration file not found: {config_file}"
                logging.error(err_msg)
                return "<Error>", err_msg

            cmd = ['uncrustify', '-c', config_file, '-f', temp_in_path, '-o', temp_out_path]
            logging.debug(f"Run commands: {' '.join(cmd)}")
                    
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=0.5)
            logging.debug(f"Uncrustify Return code: {result.returncode}")
            logging.debug(f"Uncrustify Standard output: {result.stdout}")
            logging.debug(f"Uncrustify Error output: {result.stderr}")
                
            if result.returncode != 0:
                logging.debug(f"Uncrustify error: {result.stderr}")
                return "<Error>", normalize_stderr(result.stderr)
                    
            processed_code = read_text_file(temp_out_path)
            logging.debug("The formatted code was successfully read")
 
            return processed_code, None
                
        except Exception as e:
            logging.error(f"Error in uncrustify processing: {e}")
            return "<Error>", str(e)
        finally:
            safe_cleanup(temp_in_path, temp_out_path)
            logging.debug("Temporary file deleted")

class JavaFormatter(CFamilyFormatter):
    def __init__(self):
        super().__init__()
        self.lang='java'
        #read config files
        self.formatted_config=CONFIG_PATH['java'][0]
        self.unformatted_config=CONFIG_PATH['java'][1]

        self.indent_level=2

    def format_code(self,code:str,repair_strategy:str,info:dict) -> str:
        info['tool']='uncrustify'
        formatted_code,err_msg=self._run_uncrustify(code,self.formatted_config)
        if(formatted_code!="<Error>"):
            info.update({"status":"success","original_error":None,"repair_attempted":False})
            formatted_code=self.remove_align_space(formatted_code)
            return formatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            code,remain=self.cut_incomplete_statements(code)
            code=self.close_open_string(code)
            code,appended_len=close_open_brackets(code,lang=self.lang)
            formatted_code,err_msg=self._run_uncrustify(code,self.formatted_config)
            if(formatted_code=="<Error>"):
                info['status']="failed"
                return None
            formatted_code=self.remove_align_space(formatted_code)
            formatted_code=remove_appended_brackets(formatted_code,appended_len)
            if(remain):
                # the last non-empty line's indent
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
    
    def remove_align_space(self, code):
        code=re.sub(r'(?<=\S)[ \t]+(?=//|/\*)',' ',code)
        code=re.sub(r'(public|private|final|protected|static)[ \t]+(?=class)',r'\1 ',code)
        return code

    def unformat_code(self,code:str,repair_strategy:str,info:dict) -> str:
        info['tool']='uncrustify'
        unformatted_code,err_msg=self._run_uncrustify(code,self.unformatted_config)
        if(unformatted_code!="<Error>"):
            info.update({"status":"success","original_error":None,"repair_attempted":False})
            unformatted_code=self.remove_extra_spaces_newlines(unformatted_code)
            return unformatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            code, remain=self.cut_incomplete_statements(code)
            if(remain):
                remain=self.unformat_code_re(remain)
            code=self.close_open_string(code)
            code,appended_len=close_open_brackets(code,lang=self.lang)
            unformatted_code,err_msg=self._run_uncrustify(code,self.unformatted_config)
            if(unformatted_code=="<Error>"):
                info['status']="failed"
                return None
            unformatted_code=self.remove_extra_spaces_newlines(unformatted_code)
            unformatted_code=remove_appended_brackets(unformatted_code,appended_len)
            unformatted_code+=remain
            info['status']="success"
            return unformatted_code
        else:
            logging.error(f"Unknown repair strategy: {repair_strategy}")
            raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")

    def cut_incomplete_statements(self,code:str) -> str:
        masked_code,segments=mask_protected_nodes(code,self.lang)
        end_markers=[';', '}','*/','{']
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
        return former,remain
    
    def remove_extra_spaces_newlines(self,code):
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed = re.sub(r'\s+;', ';', masked_code)
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'\s+{', '{', compressed)
        compressed = re.sub(r'{\s+', '{', compressed)
        compressed = re.sub(r'\s+}', '}', compressed)
        compressed = re.sub(r'}\s+', '}', compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#spaces at line start
        compressed = re.sub(r'[a-zA-Z0-9_]\n+[a-zA-Z0-9_]', lambda m: m.group(0).replace('\n', ' '), compressed)
        compressed = re.sub(r'\n+', '', compressed)
        compressed = re.sub(r'\s+', ' ', compressed)
        compressed = re.sub(r'([a-zA-Z0-9\'"_\)])\s+([?:])',r'\1\2',compressed)
        compressed = re.sub(r'([?:])\s+([a-zA-Z0-9\'"_\(])',r'\1\2',compressed)
        restored_code=restore_protected_nodes(compressed,segments)
        return restored_code.strip()
    
    def unformat_code_re(self,code:str,info=None) -> str:
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed = re.sub(r'\s+;', ';', masked_code) #\s includes \n
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'\s+\{', '{', compressed)
        compressed = re.sub(r'\{\s+', '{', compressed)
        compressed = re.sub(r'\s+\}', '}', compressed)
        compressed = re.sub(r'\}\s+', '}', compressed)
        compressed = re.sub(r'\s+,', ',', compressed)
        compressed = re.sub(r',\s+', ',', compressed)
        compressed = re.sub(r'[ \t]+\(', '(', compressed)
        compressed = re.sub(r'\([ \t]+', '(', compressed)
        compressed = re.sub(r'[ \t]+\)', ')', compressed)
        compressed = re.sub(r'\)[ \t]+', ')', compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#spaces at line start
        compressed = re.sub(r'[a-zA-Z0-9_]\n+[a-zA-Z0-9_]', lambda m: m.group(0).replace('\n', ' '), compressed)
        compressed = re.sub(r'\n+', '', compressed)
        compressed = re.sub(r'[ \t]+', ' ', compressed)
        compressed = re.sub(r'([a-zA-Z0-9\'"_\)\(])\s+([+\-*/=?:&%^|<>~!]+)',r'\1\2',compressed)
        compressed = re.sub(r'([+\-*/=?:&%^|<>~!]+)\s+([a-zA-Z0-9\'"_\(])',r'\1\2',compressed)
        restored_code=restore_protected_nodes(compressed,segments)
        return restored_code.strip()
    
    def format_code_re(self,code:str,info=None,initial_indent=0) -> str:
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        masked_code,segments=mask_protected_nodes(code,self.lang)
        lines=list()
        indent=initial_indent
        pattern=re.compile(r'[;\{\}]')
        remain_code=masked_code
        while(True):
            pos=pattern.search(remain_code)
            if(not pos):
                remain_code=remain_code.lstrip()
                if(remain_code.startswith('}')): indent=max(0,indent-self.indent_level)
                lines.append(" "*indent+remain_code)
                break
            cur_line=re.sub(r'(_LC>>|\n|<<PREPROCESSOR_\w*>>)[ \t]*',r"\1"+" "*indent,remain_code[:pos.start()+1])
            ch=remain_code[pos.start()]
            if(ch=='}'):
                indent=max(0,indent-self.indent_level)
            lines.append(" "*indent+cur_line.lstrip()+"\n")
            if(ch=='{'):
                indent+=self.indent_level
            remain_code=remain_code[pos.start()+1:]
        restored_code=restore_protected_nodes("".join(lines),segments)
        return restored_code.rstrip()

    def close_open_string(self,code:str):
        quotes=['"','\'']
        multiline_indicator='"""'
        masked_code,segments=mask_protected_nodes(code,self.lang)
        code_lines=masked_code.splitlines(keepends=True)
        new_lines=list()
        for line_no,line in enumerate(code_lines):
            if multiline_indicator in line:
                new_lines.extend(code_lines[line_no:])
                break
            cur_quote=None
            is_escaped=False
            new_line=""
            last_idx=0
            for idx,char in enumerate(line):
                if(is_escaped):
                    is_escaped=False
                    continue
                if(char=='\\'):
                    is_escaped=True
                    continue

                if(cur_quote and char==cur_quote):
                    cur_quote=None
                elif(not cur_quote and char in quotes):
                    cur_quote=char
                if char in ['{','}',';','\n'] and cur_quote:
                    new_line+=line[last_idx:idx]+cur_quote
                    cur_quote=None
                    last_idx=idx
            new_line+=line[last_idx:]
            if(cur_quote):
                new_line=new_line.rstrip()+cur_quote+"\n"
            new_lines.append(new_line)
        restored_code=restore_protected_nodes("".join(new_lines),segments)
        return restored_code

class CFormatter(CFamilyFormatter):
    def __init__(self):
        super().__init__()
        self.lang='c'
        #read config files
        self.formatted_config=CONFIG_PATH['c'][0]
        self.unformatted_config=CONFIG_PATH['c'][1]

        self.indent_level=2

        self.quotes=['"','\'']
        self.multiline_quotes_start=[]
        self.string_types=['char_literal','string_literal']

    def format_code(self,code:str,repair_strategy:str,info:dict) -> str:
        info['tool']='uncrustify'
        formatted_code,err_msg=self._run_uncrustify(code,self.formatted_config)
        if(formatted_code!="<Error>"):
            info.update({"status":"success","original_error":None,"repair_attempted":False})
            formatted_code=self.remove_align_space(formatted_code)
            return formatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            code,remain=self.cut_incomplete_statements(code)
            code=self.close_open_string(code)
            code,appended_len=close_open_brackets(code,lang=self.lang)
            code=self.cut_long_line(code)
            formatted_code,err_msg=self._run_uncrustify(code,self.formatted_config)
            if(formatted_code=="<Error>"):
                info['status']="failed"
                return None
            # formatted_code=self._run_uncrustify(formatted_code,self.formatted_config)
            formatted_code=self.remove_align_space(formatted_code)
            formatted_code=remove_appended_brackets(formatted_code,appended_len)
            if(remain):
                # the last non-empty line's indent
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
        info['tool']='uncrustify'
        code=self.concat_lines(code)
        unformatted_code,err_msg=self._run_uncrustify(code,self.unformatted_config)
        if(unformatted_code!="<Error>"):
            info.update({"status":"success","original_error":None,"repair_attempted":False})
            unformatted_code=self.remove_extra_spaces_newlines(unformatted_code)
            return unformatted_code
        info['original_error']=err_msg
        if(repair_strategy=='none'):
            info.update({"status":"failed","repair_attempted":False})
            return None
        elif(repair_strategy=='on_failure'):
            info['repair_attempted']=True
            code, remain=self.cut_incomplete_statements(code)
            if(remain):
                remain=self.unformat_code_re(remain)
            code=self.close_open_string(code)
            code,appended_len=close_open_brackets(code,lang=self.lang)
            unformatted_code,err_msg=self._run_uncrustify(code,self.unformatted_config)
            if(unformatted_code=="<Error>"):
                info['status']="failed"
                return None
            unformatted_code=self.remove_extra_spaces_newlines(unformatted_code)
            unformatted_code=remove_appended_brackets(unformatted_code,appended_len)
            if(unformatted_code.endswith("#endif")):
                unformatted_code+='\n'
            unformatted_code+=remain
            info['status']="success"
            return unformatted_code
        else:
            logging.error(f"Unknown repair strategy: {repair_strategy}")
            raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")

    def concat_lines(self,code):
        code_bytes=bytearray(code,'utf8')
        new_code=""
        protect_ranges=get_protect_node_range(code,self.lang)
        def in_range(pos):
            for (node_type,start,end) in protect_ranges:
                if(start<=pos<=end):
                    if node_type=='preproc_arg':
                        text=code_bytes[start:pos+1].decode("utf8")
                        if((text.count('"')-text.count('\\"'))%2!=0 or (text.count("'")-text.count("\\'"))%2!=0):
                            return True
                        else:
                            return False
                    else:
                        return True
            return False

        res=re.finditer(r'\s*\\\n\s*',code)
        last_end=0
        for r in res:
            new_code+=code[last_end:r.start()]
            pos=len(bytearray(code[:r.start()],'utf8'))
            if(in_range(pos)):
                new_code+=r.group().replace("\\\n",'') #keep spaces
            else:
                new_code+=re.sub(r'\s+',' ',r.group().replace("\\\n",''))
            last_end=r.end()
        new_code+=code[last_end:]
        return new_code

    def cut_incomplete_statements(self,code:str) -> str:
        masked_code,segments=mask_protected_nodes(code,self.lang)
        end_markers=[';', '}','*/','{','#endif']
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
        return former,remain

    def remove_extra_spaces_newlines(self,code):
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed=re.sub(r'[ \t]+',' ',masked_code)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)
        compressed = re.sub(r'[ \t]+\(', '(', compressed)
        compressed = re.sub(r'\([ \t]+', '(', compressed)
        compressed = re.sub(r'[ \t]+\)', ')', compressed)
        compressed = re.sub(r'\)[ \t]+', ')', compressed)
        masked_code2,segments2=self.protect_preprocessors(compressed)
        compressed = re.sub(r'\s+;', ';', masked_code2)
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'\s+{', '{', compressed)
        compressed = re.sub(r'{\s+', '{', compressed)
        compressed = re.sub(r'\s+}', '}', compressed)
        compressed = re.sub(r'}\s+', '}', compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#spaces at line start
        compressed = re.sub(r'_LC>>[ \t\n]+','_LC>>',compressed)
        compressed = re.sub(r'[a-zA-Z0-9_]\n+[a-zA-Z0-9_]', lambda m: m.group(0).replace('\n', ' '), compressed)
        compressed = re.sub(r'\n+', '', compressed)
        compressed = re.sub(r'\s+', ' ', compressed)
        compressed = re.sub(r'([a-zA-Z0-9\'"_\)])\s+([?:])',r'\1\2',compressed)
        compressed = re.sub(r'([?:])\s+([a-zA-Z0-9\'"_\(])',r'\1\2',compressed)
        restored_code=restore_protected_nodes(self.restore_preprocessors(compressed,segments2),segments)
        return restored_code.strip()
    
    def protect_preprocessors(self,code:str):
        # replace all lines start with # into template and restore afterwards
        template="<<PREPROCESSOR_{}_PLH>>"
        code=re.sub(r'_LC>>','_LC>>\n',code)
        lines=code.splitlines(keepends=True)
        idx=0
        segments={}
        for i,line in enumerate(lines):
            res=re.search(r'#([^/\n]|\/[^*]|\\\r?\n)*$',line)
            if(res):
                key=template.format(idx)
                segments[key]=line[res.start():].replace("_LC>>\n","_LC>>")
                lines[i]=line[:res.start()]+key
                idx+=1
            else:
                lines[i]=line.replace("_LC>>\n","_LC>>")
        return "".join(lines),segments

    def restore_preprocessors(self,code:str,segments:dict):
        # check if the char before the placeholder is _LC>> or \n, if not so, add a space to avoid midline directive
        for key,content in segments.items():
            if(not key.startswith("<<PREPROCESSOR_")):
                continue
            code=re.sub(r'(_LC>>|\n)[ \t]*'+re.escape(key), r'\1'+content, code)
            code=code.replace(key,"\n"+content)
        return code

    def unformat_code_re(self,code:str,info:dict=None):
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        code=self.concat_lines(code)
        masked_code,segments=mask_protected_nodes(code,self.lang)
        compressed=re.sub(r'[ \t]+',' ',masked_code)
        compressed = re.sub(r'\s+,', ',', compressed)
        compressed = re.sub(r',\s+', ',', compressed)
        compressed = re.sub(r'[ \t]+\(', '(', compressed)
        compressed = re.sub(r'\([ \t]+', '(', compressed)
        compressed = re.sub(r'[ \t]+\)', ')', compressed)
        compressed = re.sub(r'\)[ \t]+', ')', compressed)
        compressed=re.sub(r'#[ \t]+','#',compressed)
        masked_code2,segments2=self.protect_preprocessors(compressed)
        compressed = re.sub(r'\s+;', ';', masked_code2) #\s includes \n
        compressed = re.sub(r';\s+', ';', compressed)
        compressed = re.sub(r'\s+\{', '{', compressed)
        compressed = re.sub(r'\{\s+', '{', compressed)
        compressed = re.sub(r'\s+\}', '}', compressed)
        compressed = re.sub(r'\}\s+', '}', compressed)
        compressed = re.sub(r'\n[ \t]+','\n',compressed)#spaces at line start
        compressed = re.sub(r'[a-zA-Z0-9_]\n+[a-zA-Z0-9_]', lambda m: m.group(0).replace('\n', ' '), compressed)
        compressed = re.sub(r'\n+', '', compressed)
        compressed = re.sub(r'[ \t]+', ' ', compressed)
        compressed = re.sub(r'\s+([+\-*/=\?:&%^|<>~!]+)',r'\1',compressed)
        compressed = re.sub(r'([+\-*/=\?:&%^|<>~!]+)\s+',r'\1',compressed)
        compressed = re.sub(r'(<<PREPROCESSOR_[0-9]+_PLH>>|<<PROTECTED_[0-9]+_PLACEHOLDER_LC>>)\s+',r'\1',compressed)
        compressed = re.sub(r'[ \t]+(<<PREPROCESSOR_[0-9]+_PLH>>|<<PROTECTED_[0-9]+_PLACEHOLDER[A-Z_]*>>)',r'\1',compressed)
        restored_code=restore_protected_nodes(self.restore_preprocessors(compressed,segments2),segments)
        return restored_code.strip()
    
    def format_code_re(self,code:str,info:dict=None,initial_indent=0) -> str:
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        masked_code,segments=mask_protected_nodes(code,self.lang)
        for plh,content in segments.items():
            if(content.startswith("/*") and content.endswith("*/")):#block comment
                segments[plh]=content+"\n"
        masked_code2,segments2=self.protect_preprocessors(masked_code)
        lines=list()
        indent=initial_indent
        pattern=re.compile(r'[;\{\}]')
        remain_code=masked_code2+" "
        while(True):
            pos=pattern.search(remain_code)
            if(not pos):
                remain_code=remain_code.lstrip()
                if(remain_code.startswith('}')): indent=max(0,indent-self.indent_level)
                lines.append(" "*indent+remain_code)
                break
            cur_line=re.sub(r'(_LC>>|\n|<<PREPROCESSOR_\w*>>)[ \t]*',r"\1"+" "*indent,remain_code[:pos.start()+1])
            ch=remain_code[pos.start()]
            if(ch=='}'):
                indent=max(0,indent-self.indent_level)
            lines.append(" "*indent+cur_line.lstrip()+"\n")
            if(ch=='{'):
                indent+=self.indent_level
            remain_code=remain_code[pos.start()+1:]
        restored_code=self.restore_preprocessors("".join(lines),segments2)
        restored_code=restore_protected_nodes(restored_code,segments)
        return restored_code.rstrip()
    
    def close_open_string(self,code:str):
        code=self._fill_missing_quotes_by_tree_sitter(code)

        mask_type=PROTECT_NODES[self.lang]
        mask_type.add('number_literal')#separator
        masked_code,segments=mask_protected_nodes(code,self.lang,mask_type)
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
                if char in ['{','}',';','\n'] and cur_quote:#is_escaped will skip \\n
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
                if(child.is_missing and child.type in self.quotes and node.type in self.string_types):
                    edits.append((child.start_byte,child.type))
                elif(child.is_missing and child.type==';'):
                    edits.append((child.start_byte,child.type))
                else:
                    find_missing(child)
        find_missing(tree.root_node)
        edits=sorted(edits,key=lambda x: x[0],reverse=True)
        for pos, quote in edits:
            byte_code[pos:pos] = quote.encode('utf8')
        return byte_code.decode('utf8')


class CPPFormatter(CFormatter):
    def __init__(self):
        super().__init__()
        self.lang='cpp'
        #read config files
        self.formatted_config=CONFIG_PATH['cpp'][0]
        self.unformatted_config=CONFIG_PATH['cpp'][1]

        self.indent_level=2

        self.quotes=['"','\'']
        self.multiline_quotes_start=['R"', 'LR"', 'uR"', 'UR"', 'u8R"']
        self.string_types=['string_literal','raw_string_literal', 'char_literal']

class CSharpFormatter(CFormatter):
    def __init__(self):
        super().__init__()
        self.lang='c_sharp'
        #read config files
        self.formatted_config=CONFIG_PATH['c_sharp'][0]
        self.unformatted_config=CONFIG_PATH['c_sharp'][1]

        self.indent_level=4

        self.quotes=['"','\'']
        self.multiline_quotes_start=['@"','"""']
        self.string_types=['string_literal', 'character_literal', 'verbatim_string_literal', 'raw_string_literal']

    def cut_long_line(self, code):
        code,segments=mask_protected_nodes(code,self.lang)
        code=re.sub(r'([;\}\{])',r'\1\n',code)
        code=re.sub(r'#(if|else|endif|region|endregion|define|pragma|undef)',r'\n#\1',code)
        for plh,content in segments.items():
            if(content.startswith("/*") and content.endswith("*/")):#block comment
                segments[plh]=content+"\n"
        restored_code=restore_protected_nodes(code,segments)
        return restored_code