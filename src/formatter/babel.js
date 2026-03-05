const fs = require('fs');
const parser = require('@babel/parser');
const generate = require('@babel/generator').default;

const option = process.argv[2];
const language = process.argv[3]; //js or ts
const inputFile = process.argv[4];
const outputFile = process.argv[5];

if (!inputFile || !outputFile) {
  console.error("File path not specified.");
  process.exit(1);
}

plugins=[
  'v8intrinsic',

  'asyncDoExpressions',
  'decimal',
  'decorators',
  'decoratorAutoAccessors',
  'deferredImportEvaluation',
  'destructuringPrivate',
  'doExpressions',
  'explicitResourceManagement',
  'exportDefaultFrom',
  'functionBind',
  'functionSent',
  'importReflection',
  'moduleBlocks',
  ['optionalChainingAssign', {version: '2023-07'}],
  'partialApplication',
  ['pipelineOperator', { proposal: 'fsharp' }],
  'recordAndTuple',
  'sourcePhaseImports',
  'throwExpressions'
];

try {
  const code = fs.readFileSync(inputFile, 'utf8');

  if(language=='javascript' || language=='js'){
    plugins.push('jsx')
    plugins.push('flow');
  }
  else if(language=='typescript' || language=='ts'){
    plugins.push('typescript');
  }
  else if (language=='tsx'){
    plugins.push('jsx');
    plugins.push('typescript');
  }
  else{
    console.error("Unsupported language:", language);
    process.exit(1);
  }

  const ast = parser.parse(code, {
    sourceType: 'module',
    plugins: plugins,
    attachComment: true,
    allowImportExportEverywhere: true,
    allowAwaitOutsideFunction: true,
    allowYieldOutsideFunction: true,
    allowNewTargetOutsideFunction: true,
    allowReturnOutsideFunction: true,
    allowSuperOutsideMethod: true,
    allowUndeclaredExports: true,
    
    errorRecovery: true
  });

  if(option==='unformat'){
    output = generate(ast, {
      compact: true,
      concise: true,
      minified: true,
      comments: true,
      retainLines: false,
      jsescOption: {
        minimal: true,//minimal escape
      }
    }, code);
  }else if(option==='format'){
    output = generate(ast, {
      compact: false,       
      minified: false,       
      comments: true,       
      retainLines: false,
      jsescOption: {
        minimal: true
      }
    }, code);
  }else{
    console.error("Unsupported option.");
    process.exit(1);
  }

  fs.writeFileSync(outputFile, output.code);

} catch (err) {
  console.error(err.message);
  if (err.loc) {
    console.error(`Error location: line ${err.loc.line}, column ${err.loc.column}`);
  }
}