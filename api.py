from flask import Flask,request,jsonify,g
import re
import logging
logging.basicConfig(level=logging.DEBUG)
import time
import json
guess=None

from src.formatter.get_formatter import get_formatter,FORMATTER_MAP,LANGUAGE_NAME_MAP
from src.extract_code import extract_content,DEFAULT_EXTRACT_CONFIG

app=Flask(__name__)

@app.before_request
def start_timer():
    g.start_time=time.time()

@app.after_request
def log_request(response):
    if hasattr(g, 'start_time'):
        latency = (time.time() - g.start_time) * 1000
        app.logger.info(f"{request.method} {request.path} took {latency:.2f} ms")
    if(response.is_json):
        data=json.loads(response.get_data())
        data['response_time_ms']=latency
        response.set_data(json.dumps(data))
    return response

def process_code_request(data, with_lang_func, without_lang_func):
    input_text = data.get("input")
    mode = data.get("mode", "mixed")
    repair_strategy = data.get("repair_strategy", "on_failure")
    if mode == "code":
        lang = data.get("language", None)
        if not lang:
            result = without_lang_func(input_text, repair_strategy)
        else:
            lang = lang.lower()
            if lang not in LANGUAGE_NAME_MAP:
                return {"Error": f"Language {lang} is not supported."}
            logging.debug(f"Processing with language info: {lang}")
            result = with_lang_func(input_text, LANGUAGE_NAME_MAP[lang], repair_strategy)
        return {"segments": [result]}
    elif mode == "mixed":
        default_lang = data.get("language", None)
        if default_lang and default_lang.lower() not in LANGUAGE_NAME_MAP:
            return {"Error": f"Language {default_lang} is not supported."}
        default_lang = LANGUAGE_NAME_MAP[default_lang.lower()] if default_lang else None
        config = {**DEFAULT_EXTRACT_CONFIG, **data.get("config", {})}
        segments = extract_content(input_text, **config)
        processed_segments = []
        for segment in segments:
            if segment['type'] == 'text':
                processed_segments.append(segment)
            else:
                lang = segment.get("lang")
                if not lang:
                    if default_lang:
                        logging.debug(f"Default language used: {default_lang}")
                        result = with_lang_func(segment['content'], default_lang, repair_strategy)
                    else:
                        logging.debug("Processing without language info.")
                        result = without_lang_func(segment['content'], repair_strategy)
                elif lang.lower() not in LANGUAGE_NAME_MAP:
                    result = {"type": "code", "content": segment['content'], "language": lang, "meta_info": {"status": "failed", "original_error": f"Language {lang} is not supported."}}
                else:
                    result = with_lang_func(segment['content'], LANGUAGE_NAME_MAP[lang.lower()], repair_strategy)
                processed_segments.append(result)
        return {"segments": processed_segments}
    else:
        return {"Error": f"Invalid mode: {mode}. Supported modes are 'code' and 'mixed'."}

@app.route('/unformat_code',methods=['POST'])
def unformat_code_api():
    try:
        data = request.get_json()
        if(data is None or "input" not in data):
            return jsonify({"Error":"No data received."}), 400
        logging.debug(f"Unformat API received:{data}")

        response_data = process_code_request(data, unformat_with_language_info, unformat_without_language_info)
        if "Error" in response_data:
            return jsonify(response_data), 400
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"Error":str(e)}), 400

def unformat_with_language_info(code,lang,repair_strategy):
    logging.debug("unformat_with_language_info:"+lang)
    formatter=get_formatter(lang)
    unformat_info={"language_info":True}
    unformatted_code=formatter.unformat_code(code,repair_strategy,unformat_info)
    if(not unformatted_code):
        logging.debug("unformat_code_re:"+lang)
        unformatted_code=formatter.unformat_code_re(code,unformat_info)
    del unformat_info['language_info']
    return {"type":"code","content":unformatted_code,"language":lang,"meta_info":unformat_info}

def get_prob_langs(code):
    global guess
    if(not guess):
        if("ENABLE_GUESS_LANG" not in os.environ or not os.getenv("ENABLE_GUESS_LANG")):
            err_msg="The language is not provided and automatic language inference (Guesslang) is not enabled. Please set environment variable ENABLE_GUESS_LANG to True to enable Guesslang or provide the language info in the request."
            raise Exception(err_msg)
        try:
            from guesslang import Guess
        except ImportError as e:
            err_msg="Import Guesslang failed: "+str(e)
            logging.error(err_msg)
            raise Exception(err_msg)
        guess=Guess()
        logging.debug("Initialised Guesslang model.")
    probs = guess.probabilities(code)
    logging.debug("Guess probs:"+str(probs))

    top_p=0.9
    probs.sort(key=lambda x: x[1],reverse=True)
    cumulative_prob=0
    for i,(lang,prob) in enumerate(probs):
        cumulative_prob+=prob
        if(cumulative_prob>=top_p):
            break
    langs=[it[0] for it in probs[:i+1] if it[0].lower() in LANGUAGE_NAME_MAP]
    if('TypeScript' in langs and re.search(r'from[ \t]+["\']react["\']',code)):
        idx=langs.index('TypeScript')
        langs.insert(idx,'tsx')
    return langs

def unformat_without_language_info(code,repair_strategy):
    prob_langs=get_prob_langs(code)
    logging.debug("probable languages:"+str(prob_langs))
    for lang in prob_langs:
        formatter=get_formatter(lang)
        if(not formatter):
            continue
        unformat_info={"language_info":False}
        unformatted_code=formatter.unformat_code(code,repair_strategy,unformat_info)
        if(unformatted_code):
            logging.debug("unformat code success:"+lang)
            del unformat_info['language_info']
            return {"type":"code","content":unformatted_code,"language":lang,"meta_info":unformat_info}
    # no lang succeed
    return {"type":"code","content":code,"language":None,"meta_info":{"status":"failed","original_error":"Unable to unformat code with inferred languages."}}

@app.route('/format_code',methods=['POST'])
def format_code_api():
    try:
        data = request.get_json()
        if(data is None or "input" not in data):
            return jsonify({"Error":"No data received."}), 400
        logging.debug(f"Format API received:{data}")

        response_data = process_code_request(data, format_with_language_info, format_without_language_info)
        if "Error" in response_data:
            return jsonify(response_data), 400
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"Error":str(e)}), 400

def format_with_language_info(code,lang,repair_strategy):
    formatter=get_formatter(lang)
    format_info={"language_info":True}
    formatted_code=formatter.format_code(code,repair_strategy,format_info)
    if(not formatted_code):
        logging.debug("format_code_re:"+lang)
        formatted_code=formatter.format_code_re(code,format_info)
    del format_info['language_info']
    return {"type":"code","content":formatted_code,"language":lang,"meta_info":format_info}

def format_without_language_info(code,repair_strategy):
    prob_langs=get_prob_langs(code)
    logging.debug("probable languages:"+str(prob_langs))
    for lang in prob_langs:
        formatter=get_formatter(lang)
        if(not formatter):
            continue
        format_info={"language_info":False}
        formatted_code=formatter.format_code(code,repair_strategy,format_info)
        if(formatted_code):
            logging.debug("format code success:"+lang)
            del format_info['language_info']
            return {"type":"code","content":formatted_code,"language":lang,"meta_info":format_info}
    return {"type":"code","content":code,"language":None,"meta_info":{"status":"failed","original_error":"Unable to format code with inferred languages."}}

if __name__=="__main__":
    import os
    if(os.getenv("ENABLE_GUESS_LANG",False)):
        try:
            from guesslang import Guess
        except ImportError as e:
            logging.error("Import Guesslang failed:"+str(e))
            raise e
        guess=Guess()
    app.run(host="0.0.0.0",port=5089)
