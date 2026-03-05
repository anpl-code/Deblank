package main

import (
    "fmt"
    "go/scanner"
    "go/token"
	"os"
)

func main(){
	if len(os.Args)<2{
        return
    }

    input_path:=os.Args[1]
    output_path:=input_path+".out"

    src,err:=os.ReadFile(input_path)
    if(err!=nil){
        fmt.Fprintf(os.Stderr,"Error reading input: %v\n",err)
        return
    }

    out_file, err := os.Create(output_path)
    if(err!=nil){
        fmt.Fprintf(os.Stderr,"Error creating output file:%v\n",err)
        return
    }

    defer out_file.Close()

    errorCount:=0
    errorHandler := func(pos token.Position, msg string) {
        errorCount++
		fmt.Printf("Error %s: %s\n",pos,msg)
	}

    var s scanner.Scanner
    fset := token.NewFileSet()           // positions are relative to fset
    file := fset.AddFile("", fset.Base(), len(src))
    s.Init(file, []byte(src), errorHandler, scanner.ScanComments)

    var last_token token.Token
    var hasLast bool = false

    _, next_token, next_lit:=s.Scan() //pos, tok, lit
    for {
        cur_token, lit:=next_token,next_lit
        
        if cur_token == token.EOF {
            break
        }
        _, next_token, next_lit=s.Scan()

        if hasLast{
            if(requireSpace(last_token,cur_token)){
                fmt.Fprint(out_file," ")
            }
        }
        if cur_token == token.SEMICOLON{
            if(next_token!=token.RBRACE){
                fmt.Fprint(out_file,";")
            }
        } else if cur_token == token.COMMENT {
            fmt.Fprint(out_file,lit)
            if(lit[0]=='/' && lit[1]=='/'){// line comment
                fmt.Fprint(out_file,"\n")
            }
        } else if lit!=""{
            fmt.Fprint(out_file,lit) //identifier
        } else{
            fmt.Fprint(out_file,cur_token.String())
        }

        last_token=cur_token
        hasLast=true
    }
}

func requireSpace(prev token.Token, cur token.Token) bool {
    if((isKeywordOrIdent(prev) && isKeywordOrIdent(cur)) ||
        (isKeywordOrIdent(prev) && cur.IsLiteral()) ||
        (identicalOp(prev,cur))){
        return true
    }
    return false
}

func isKeywordOrIdent(t token.Token) bool {
    return t == token.IDENT || t.IsKeyword() || t == token.STRING || t == token.CHAR
}

func identicalOp(prev,cur token.Token) bool {//token.IsOperator contains delimiter
    if((prev==token.ADD || prev==token.INC) && (cur==token.ADD || cur==token.INC)){
        return true
    }
    if((prev==token.SUB || prev==token.DEC) && (cur==token.SUB || cur==token.DEC)){
        return true
    }
    return false
}