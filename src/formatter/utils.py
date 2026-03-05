from tree_sitter_languages import get_parser

BRACKET_PAIRS={ '(': ')', '[': ']', '{': '}' }

def close_open_brackets(code,bracket_pairs=None,lang=None):
    code,segments=mask_protected_nodes(code,lang)   
    if bracket_pairs is None:
        bracket_pairs = BRACKET_PAIRS
    stack = []
    for char in code:
        if char in bracket_pairs.keys():
            stack.append(bracket_pairs[char])
        elif char in bracket_pairs.values():
            if stack and char == stack[-1]:
                stack.pop()
    appended_len=len(stack)
    while stack:
        code += stack.pop()
    code=restore_protected_nodes(code,segments)
    return code,appended_len

def detect_open_brackets(code,bracket_pairs=None,lang=None):
    code,segments=mask_protected_nodes(code,lang)   
    if bracket_pairs is None:
        bracket_pairs = BRACKET_PAIRS
    stack = []
    line_no=0
    for i,char in enumerate(code):
        if(char=='\n'):
            line_no+=1
        if char in bracket_pairs.keys():
            stack.append((bracket_pairs[char], line_no, code[i-20:i+20]))
        elif char in bracket_pairs.values():
            if stack and char == stack[-1][0]:
                stack.pop()
    appended_len=len(stack)
    while stack:
        print("Unclosed bracket:",stack.pop())
    code=restore_protected_nodes(code,segments)
    return code,appended_len

def remove_appended_brackets(code,appended_len,ignore_elems=[]):
    if(appended_len<=0):
        return code
    # ignore space and newlines at the end
    ignore_elems.extend([' ','\n','\t','\r'])
    for i in range(len(code)-1,-1,-1):
        if(code[i] not in ignore_elems):
            appended_len-=1
            if(appended_len==0):
                return code[:i]

PROTECT_NODES={
    'cpp': {
        'comment', 
        'system_lib_string', 'preproc_arg',
        'string_literal','raw_string_literal', 'char_literal'
    },
    'java': {
        'line_comment', 'block_comment', 'string_literal',
        'character_literal',
    },
    'python': {
        'comment', 'string', 'decorator'
    },
    'c_sharp': {
        'comment', 'string_literal', 'character_literal', 
        'verbatim_string_literal', 'raw_string_literal',
        'interpolated_string_expression', 'preproc_arg',
        'preproc_string_literal'
    },
    'c':{
        'comment',
        'preproc_arg',
        'string_literal','system_lib_string', 'char_literal'
    },
    'javascript':{
        'comment','html_comment',
        'string', 'template_string',
        'regex','jsx_text'
    },
    'typescript':{
        'comment','html_comment',
        'string','template_string',
        'regex'
    },
    'tsx':{
        'comment','html_comment',
        'string','template_string',
        'regex','jsx_text'
    },
    'go':{
        'comment','raw_string_literal','interpreted_string_literal'
    }
}

LINE_COMMENT_NODES={
    'c': {'comment'},
    'cpp': {'comment'},
    'java': {'line_comment'},
    'python':{'comment','decorator'},
    'c_sharp':{'comment'},
    'javascript':{'comment','html_comment'},
    'typescript':{'comment','html_comment'},
    'tsx':{'comment','html_comment'},
    "go":{"comment"}
}

def mask_protected_nodes(code:str,language:str,protected_nodes=None) -> str:
    parser=get_parser(language)
    tree=parser.parse(bytes(code,'utf8'))
    root_node=tree.root_node
    if(protected_nodes is None):
        protected_nodes=PROTECT_NODES.get(language,set())
    if not protected_nodes:
        return code,{}
    code_bytes=bytearray(code,'utf8')
    protected_range=[]
    segments={}
    def mask_node(node):
        if node.type in protected_nodes:
            protected_range.append((node.type,node.start_byte,node.end_byte))#no overlap
        else:
            for child in node.children:
                mask_node(child)
    mask_node(root_node)
    replacements=sorted(protected_range,key=lambda x:x[1],reverse=True)
    for i,(node_type,start_byte,end_byte) in enumerate(replacements):
        ori_content=code_bytes[start_byte:end_byte].decode('utf8')
        if(is_line_comment_node(node_type,ori_content,language)):
           ori_content=ori_content+'\n'
           end_byte+=1 # end byte extend to end of \n sequence
           placeholder=get_mask_template(i,'_LC')
        else:
            placeholder=get_mask_template(i)
        segments[placeholder]=ori_content
        code_bytes[start_byte:end_byte]=bytes(placeholder,'utf8')
    return code_bytes.decode('utf8'),segments

def get_mask_template(i,suffix=''):
    return f"<<PROTECTED_{i}_PLACEHOLDER{suffix}>>"

def restore_protected_nodes(code:str,segments:dict) -> str:
    for placeholder,ori_content in segments.items():
        code=code.replace(placeholder,ori_content)
    return code

def is_line_comment_node(node_type,content,language):
    if(node_type not in LINE_COMMENT_NODES.get(language,set())):
        return False
    if(language in ['c','cpp','c_sharp','javascript','typescript','tsx','go']):
        if(node_type=='html_comment'):
            return True
        return content.startswith("//")
    return True

def get_specific_node(code:str,language:str,node_types:set,cascade=False):
    if not node_types:
        return []
    parser=get_parser(language)
    tree=parser.parse(bytes(code,'utf8'))
    root_node=tree.root_node
    nodes=[]
    def mask_node(node):
        if node.type in node_types:
            nodes.append(node)
        if node.type not in node_types or cascade:
            for child in node.children:
                mask_node(child)
    mask_node(root_node)
    return nodes

def get_specific_node_range(code:str,language:str,node_types:set):
    if not node_types:
        return []
    parser=get_parser(language)
    tree=parser.parse(bytes(code,'utf8'))
    root_node=tree.root_node
    ranges=[]
    def mask_node(node):
        if node.type in node_types:
            ranges.append((node.type,node.start_byte,node.end_byte))#no overlap
        else:
            for child in node.children:
                mask_node(child)
    mask_node(root_node)
    return ranges

def get_protect_node_range(code:str,language:str) -> str:
    protected_nodes=PROTECT_NODES.get(language,set())
    return get_specific_node_range(code,language,protected_nodes)

class RepairUnableError(Exception):
    pass