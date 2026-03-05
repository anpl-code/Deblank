package main

import (
	"go/scanner"
	"go/token"
	"os"
	"fmt"
)

func cutIncompleteStatement(src []byte) ([]byte,[]byte){//success: write to different file; fail: output message to stderr
	fset:=token.NewFileSet()
	file:=fset.AddFile("",fset.Base(),len(src))

	errorHandler := func(pos token.Position, msg string) {
		fmt.Printf("Error %s: %s\n",pos,msg)
	}

	var s scanner.Scanner
	s.Init(file,src,errorHandler,scanner.ScanComments)
	var(
		lastPos token.Pos=0 //last ; { }
	)

	for{
		pos,tok,_:=s.Scan()
		if tok==token.EOF{
			break
		}
		if tok==token.ILLEGAL{
			fmt.Fprintf(os.Stderr,"Illegal token in code.")
			return nil,nil
		}
		if tok==token.LBRACE || tok==token.RBRACE || tok==token.SEMICOLON{
			fmt.Printf("%s\t%-10s\n", fset.Position(pos), tok)
			lastPos=pos+1
		}
	}

	var formerLen int
	if(lastPos==0){
		formerLen=len(src)
	} else if lastPos>token.Pos(len(src)){
		formerLen=len(src)
	} else{
		formerLen=file.Offset(lastPos)
	}
	former:=src[:formerLen]
	remain:=src[formerLen:]

	return former, remain
}

func main(){
	if len(os.Args)<2{
        return
    }

    input_path:=os.Args[1]
	src,err:=os.ReadFile(input_path)
    if(err!=nil){
        fmt.Fprintf(os.Stderr,"Error reading input: %v\n",err)
        return
    }
	output_former:=input_path+".former.out"
	output_remain:=input_path+".remain.out"

	former,remain:=cutIncompleteStatement(src)
	if(former!=nil && remain!=nil){
		out1,err1:=os.Create(output_former)
		if(err1!=nil){
			fmt.Fprintf(os.Stderr,"Error creating output file:%v\n",err1)
        	return
		}
		out2,err2:=os.Create(output_remain)
		if(err2!=nil){
			fmt.Fprintf(os.Stderr,"Error creating output file:%v\n",err2)
        	return
		}
		defer out1.Close()
		defer out2.Close()

		out1.Write(former)
		out2.Write(remain)
	}
}