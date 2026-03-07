from .base import BaseFormatter
from .utils import close_open_brackets,remove_appended_brackets,mask_protected_nodes,restore_protected_nodes,RepairUnableError

import tokenize
from io import StringIO
import logging
from yapf.yapflib.yapf_api import FormatCode
from yapf.yapflib.errors import YapfError
from yapf.pytree import pytree_utils
import re


class PythonFormatter(BaseFormatter):
    def __init__(self):
        self.style_config = {
            'based_on_style': 'pep8',
            'spaces_before_comment': 2,
            'split_before_logical_operator': True,
            'column_limit': 100,
            'indent_width': 4,
        }
        self.reducer=SpaceReducer("")
        self.max_repair_attempts=10

    def format_code(self,code:str,repair_strategy:str,info:dict) -> str:
        info['tool']='yapf'
        try:
            formatted_code, changed = FormatCode(code,style_config=self.style_config)
            info['status']='success'
            info['repair_attempted']=False
            info['original_error']=None
            return formatted_code
        except YapfError as e:
            logging.debug(f"YAPF formatting error: {e}")
            info['original_error']="YAPF error "+str(e)
            if(repair_strategy=='none'):
                info['repair_attempted']=False
                info['status']='failed'
                return None
            elif(repair_strategy=='on_failure'):
                info['repair_attempted']=True
                code,remain=self.cut_incomplete_statements(code)
                if(remain): remain=self.format_code_re(remain)
                if(not code.strip()): return remain
                end_char=code[-1]
                try:
                    code,repair_info=self.repair_syntax_error(code)
                    formatted_code,changed=FormatCode(code,style_config=self.style_config)
                    if(repair_info['empty_control']):
                        formatted_code=self.restore_empty_control_structure(formatted_code)
                    if(repair_info['suffix_len']>0):
                        formatted_code=remove_appended_brackets(formatted_code,repair_info['suffix_len'])
                    if(end_char=='\n' and formatted_code[-1]!='\n'):
                        formatted_code+='\n'
                    info['status']='success'
                    return formatted_code+remain
                except (YapfError,RepairUnableError) as e2:
                    info['status']='failed'
                    return None
            else:
                logging.error(f"Unknown repair strategy: {repair_strategy}")
                raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")
    
    def format_code_re(self,code:str,info:dict=None) -> str:
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        #add spaceline before class & function definition
        lines=code.splitlines()
        new_lines=[]
        for i,line in enumerate(lines):
            stripped=line.lstrip()
            if(stripped.startswith("class ") or stripped.startswith("def ")):
                if(i>0 and lines[i-1].strip()!=""):
                    new_lines.append("")
            new_lines.append(line)
        return "\n".join(new_lines).rstrip()

    def unformat_code(self,code:str,repair_strategy:str,info:dict) -> str:
        info['tool']='tokenize'
        try:
            self.reducer.set_source(code)
            unformatted_code=self.reducer.reduce_spaces()
            info['status']='success'
            info['repair_attempted']=False
            info['original_error']=None
            return unformatted_code
        except Exception as e:
            info['original_error']=str(e)
            if(repair_strategy=='none'):
                info['repair_attempted']=False
                info['status']='failed'
                return None
            elif(repair_strategy=='on_failure'):
                info['repair_attempted']=True
                code,remain=self.cut_incomplete_statements(code)
                if(remain): remain=self.unformat_code_re(remain)
                if(not code.strip()): return remain
                end_char=code[-1]
                try:
                    code,repair_info=self.repair_syntax_error(code)
                    self.reducer.set_source(code)
                    unformatted_code=self.reducer.reduce_spaces()
                except Exception as e:
                    info['status']='failed'
                    return None
                if(repair_info['empty_control']):
                    unformatted_code=self.restore_empty_control_structure(unformatted_code)
                if(repair_info['suffix_len']>0):
                    unformatted_code=unformatted_code.rstrip()[:-repair_info['suffix_len']]
                if(end_char=='\n' and unformatted_code[-1]!='\n'):
                    unformatted_code+='\n'
                info['status']='success'
                return unformatted_code+remain
            else:
                logging.error(f"Unknown repair strategy: {repair_strategy}")
                raise NotImplementedError(f"Unknown repair strategy: {repair_strategy}")
    
    def unformat_code_re(self,code:str,info:dict=None) -> str:
        if(info is not None):
            info['status']='regex'
            info['tool']='regex'
        masked_code,segments=mask_protected_nodes(code,"python")
        #reduce multiple spaces & spaces around operator
        masked_code=re.sub(r'_LC>>','_LC>>\n',masked_code)
        compressed=re.sub(r'(?<!\n)(?<=\S)[ \t]+', ' ', masked_code)
        compressed=re.sub(r'(?<=\S)[ \t]+([,=:>+\-\*\(\)\]\[\{\}@/%|&\^!~]+)',r'\1',compressed)
        compressed=re.sub(r'([,=:<>+\-\*\(\)\]\[\{\}@/%|&\^!~]+)[ \t]+',r'\1',compressed)
        compressed=re.sub(r'\n[ \n\t]*\n+','\n',compressed)
        compressed=re.sub(r"_LC>>\n",'_LC>>',compressed)
        restored_code=restore_protected_nodes(compressed,segments)
        return restored_code.rstrip()
    
    def repair_syntax_error(self,code):
        origin_code=code
        prev_error=None
        repair_info={"empty_control":False,"suffix_len":0}
        for _ in range(self.max_repair_attempts):
            try:
                pytree_utils.ParseCodeToTree(code)
                return code,repair_info
            except Exception as e:
                if(prev_error and 
                   e.__class__==prev_error.__class__ and e.args==prev_error.args):#cannot be fixed
                    logging.debug("Cannot fix the syntax error.")
                    raise RepairUnableError
                prev_error=e
                if(isinstance(e,IndentationError)):
                    code=self.process_indentation_error(code,e.lineno,e.offset,repair_info)
                    continue
                elif(isinstance(e,SyntaxError)):
                    if(e.msg=="invalid syntax"):
                        raise RepairUnableError
                    if(e.msg=='expected \':\''):
                        code=self.process_missing_colon(code,e.lineno,e.offset,repair_info)
                        continue
                    if(e.msg in ["'(' was never closed", "'[' was never closed", "'{' was never closed"]):
                        code,appended_len=close_open_brackets(code,lang='python')
                        repair_info["suffix_len"]+=appended_len
                        continue
                    if(e.msg.startswith("unterminated string literal")):
                        code=self.close_open_string(code,e.lineno)
                        continue
                elif('EOF in multi-line statement' in e.args):
                    code,appended_len=close_open_brackets(code,lang='python')
                    repair_info["suffix_len"]+=appended_len
                    continue
                elif('EOF in multi-line string' in e.args):
                    raise RepairUnableError
                raise RepairUnableError
        logging.debug("Max repair attempts reached.")
        raise RepairUnableError
    
    def process_empty_control_structure(self,code,lineno,offset):#add temporary placeholder
        code_lines=code.splitlines()
        #find the previous non-empty line
        for i in range(lineno-2,-1,-1):
            if(code_lines[i].strip() and not code_lines[i].strip().startswith("#")):
                if(code_lines[i].rstrip().endswith(":")):
                    code_lines[i]+=' "[EMPTY_CONTROL_PLACEHOLDER]"'
                break
        return "\n".join(code_lines)
    
    def restore_empty_control_structure(self,code):
        #if the line becomes empty, remove it
        code_lines=code.splitlines()
        cleaned_lines=[]
        for line in code_lines:
            if(line.strip()=='"[EMPTY_CONTROL_PLACEHOLDER]"'):
                continue
            else:
                cleaned_lines.append(line.replace('"[EMPTY_CONTROL_PLACEHOLDER]"','').rstrip())
        return "\n".join(cleaned_lines)
    
    def process_missing_colon(self,code,lineno,offset,repair_info):
        code_lines=code.splitlines()
        if(lineno-1<len(code_lines)):
            line=code_lines[lineno-1]
            #insert colon at the end of the line
            code_lines[lineno-1]=line.rstrip()+':'
        if(lineno==len(code_lines)):
            repair_info['suffix_len']+=1
        return "\n".join(code_lines)
    
    def process_indentation_error(self,code,lineno,offset,repair_info):
        code_lines=code.splitlines()
        if(lineno==len(code_lines) and code_lines[-1].rstrip()[-1]==':'):#empty control structure at the end of file
            code_lines[-1]+=' "[EMPTY_CONTROL_PLACEHOLDER]"'
            repair_info["empty_control"]=True
            return "\n".join(code_lines)
        #find the previous non-empty line
        for i in range(lineno-2,-1,-1):
            if(code_lines[i].strip() and not code_lines[i].strip().startswith("#")):
                if(code_lines[i].rstrip().endswith(":")):#empty control structure
                    code_lines[i]+=' "[EMPTY_CONTROL_PLACEHOLDER]"'
                    repair_info["empty_control"]=True
                    break
                else:
                    #add indentation to the current line
                    prev_indent_len=len(code_lines[i])-len(code_lines[i].lstrip())
                    cur_indent_len=len(code_lines[lineno-1])-len(code_lines[lineno-1].lstrip())
                    if(prev_indent_len<=cur_indent_len):
                        indent_len=prev_indent_len
                    else:
                        #find the nearest previous line with less indentation
                        for j in range(i-1,-1,-1):
                            if(code_lines[j].strip() and not code_lines[j].strip().startswith("#")):
                                indent_len=len(code_lines[j])-len(code_lines[j].lstrip())
                                if(indent_len<cur_indent_len):
                                    break
                    code_lines[lineno-1]=' '*indent_len+code_lines[lineno-1].lstrip()
                    break
        return "\n".join(code_lines)
    
    def cut_incomplete_statements(self,code):
        end_markers=['"""',"'''","\n"]
        last_pos=-1
        for marker in end_markers:
            pos=code.rfind(marker)
            if(pos!=-1):
                pos+=len(marker) - 1 #include the marker
                if (pos>last_pos):
                    last_pos=pos
        if(last_pos==-1):
            former=code
            remain=""
        else:
            former=code[:last_pos+1]
            remain=code[last_pos+1:]
        return former,remain
    
    def close_open_string(self,code:str,line_no):
        code_lines=code.splitlines(keepends=True)
        line_no=line_no-1
        err_line=code_lines[line_no]
        quotes=['"','\'','`']
        cur_quote=None
        is_escaped=False
        new_line=""
        last_idx=0
        for idx,char in enumerate(err_line):
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
            if char in [';','\n'] and cur_quote:
                new_line+=err_line[last_idx:idx]+cur_quote
                cur_quote=None
                last_idx=idx
        new_line+=err_line[last_idx:]
        if(cur_quote):
            new_line=new_line.rstrip()+cur_quote+"\n"
        new_lines=code_lines[:line_no]+[new_line]+code_lines[line_no+1:]
        return "".join(new_lines)

class SpaceReducer:
    def __init__(self, source: str):
        self.set_source(source)

    def set_source(self,source:str):
        self.source=source
        if(source):
            self._tokenize_source()
        else:
            self.tokens=[]

    def _tokenize_source(self):
        """Word segmentation of source code"""
        try:
            token_gen = tokenize.generate_tokens(StringIO(self.source).readline)#based on Python grammar
            self.tokens = list(token_gen)
        except tokenize.TokenError as e:
            logging.debug(f"Word segmentation error: {e}")
            raise

    def _handle_empty_control_structure(self, token_idx):
        """Handle empty control structures"""
        if token_idx + 1 < len(self.tokens):
            next_token = self.tokens[token_idx + 1]
            if next_token.type in (tokenize.NEWLINE, tokenize.NL):
                return True
        return False

    def reduce_spaces(self) -> str:
        result = []
        prev_token = None
        line_start = True
        previous_was_newline = False
        
        for i, token in enumerate(self.tokens):
            tok_type = token.type
            tok_string = token.string
            start = token.start

            if line_start and tok_type not in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
                if prev_token and prev_token.end[0] != start[0]:
                    result.append(' ' * start[1])
                line_start = False

            if tok_type in (tokenize.NEWLINE, tokenize.NL):
                if not previous_was_newline:
                    result.append('\n')
                    previous_was_newline = True
                line_start = True
            elif tok_type == tokenize.COMMENT:
                if prev_token and prev_token.type not in (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT):
                    result.append(' ')
                result.append(tok_string)
                previous_was_newline = False
            elif tok_type == tokenize.STRING:
                if(tok_string[0].isalpha()):# f""
                    result.append(' ')
                result.append(tok_string)
                previous_was_newline = False
            elif tok_type == tokenize.OP:
                result.append(tok_string)
                previous_was_newline = False
            elif tok_type in (tokenize.NAME, tokenize.NUMBER):
                # if tok_type == tokenize.NAME and tok_string in ('if', 'while', 'for') and self._handle_empty_control_structure(i):
                #     result.append(tok_string)
                # else:
                if prev_token and prev_token.type in (tokenize.NAME, tokenize.NUMBER):
                    result.append(' ')
                result.append(tok_string)
                previous_was_newline = False
            elif tok_type in (tokenize.INDENT, tokenize.DEDENT):
                continue
            else:
                result.append(tok_string)
                previous_was_newline = False

            prev_token = token

        processed = ''.join(result)
        lines = processed.splitlines()
        
        cleaned_lines = []
        blank_line = False
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if not blank_line:
                    cleaned_lines.append('')
                    blank_line = True
            else:
                cleaned_lines.append(stripped)
                blank_line = False
                
        return '\n'.join(cleaned_lines) + '\n'