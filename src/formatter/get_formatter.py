from .formatter_c import CFormatter,CPPFormatter,CSharpFormatter,JavaFormatter
from .formatter_py import PythonFormatter
from .formatter_js import JSFormatter,TSFormatter,TSXFormatter
from .formatter_go import GoFormatter

LANGUAGE_NAME_MAP={
    'c':'C',
    
    'c++':'C++',
    'cpp':'C++',
    
    'c#':'C#',
    'csharp':'C#',
    'c_sharp':'C#',
    
    'java':'Java',

    'python':'Python',

    'javascript':'JavaScript',
    'js':'JavaScript',
    'jsx':'JavaScript',

    'typescript':'TypeScript',
    'ts':'TypeScript',
    'tsx':'tsx',

    'go': 'Go'
}

FORMATTER_MAP={
    'C':CFormatter,
    'C++':CPPFormatter,
    'C#':CSharpFormatter,
    'Java':JavaFormatter,
    'Python':PythonFormatter,
    'JavaScript':JSFormatter,
    'TypeScript':TSFormatter,
    'tsx':TSXFormatter,
    'Go':GoFormatter
}

def get_formatter(language):
    if(language not in FORMATTER_MAP):
        raise RuntimeError(f"Unsupported language: {language}")
    formatter_cls=FORMATTER_MAP[language]
    if(not formatter_cls.check_prereq()):
        raise RuntimeError(f"Prerequisite check failed for formatter: {language}")
    return formatter_cls()