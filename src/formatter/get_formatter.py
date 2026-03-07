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
        raise RuntimeError(f"Language {language} is not supported.")
    formatter_cls=FORMATTER_MAP[language]
    if(not formatter_cls.check_prereq()):
        raise RuntimeError(f"Language {language} is not enabled. Please set up the environment variable to enable the support for this language. Refer to the documentation for more details.")
    return formatter_cls()