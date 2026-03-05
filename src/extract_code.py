import re

DEFAULT_EXTRACT_CONFIG={
    "start_tag":"```",
    "end_tag":"```",
    "language_tag":True
}

def extract_content(text, start_tag="```", end_tag="```",language_label=True,**kwargs): #use re
    s = re.escape(start_tag)
    e = re.escape(end_tag)
    
    pattern = f"({s})(.*?)({e})"
    
    results = []
    last_pos = 0
    
    for match in re.finditer(pattern, text, re.DOTALL):
        pre_text = text[last_pos:match.start()].strip()
        if pre_text:
            results.append({"type": "text", "content": pre_text})
        
        code_content = match.group(2)
        lang_label=None
        if(language_label):
            res=re.search(r'^([ \{\t]+)?([\w\+\#_]+)([ \}\t]+)?\n',code_content)
            if(res):
                lang_label=res.group(2).strip()
                code_content=code_content[res.end():]
        results.append({"type": "code", "content": code_content,"lang":lang_label})
        
        last_pos = match.end()
    
    post_text = text[last_pos:].strip()
    if post_text:
        results.append({"type": "text", "content": post_text})
        
    return results