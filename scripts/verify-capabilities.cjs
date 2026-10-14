// Representative behavior inventory, not a claim of complete function compatibility.
const { KernelClient } = require('../kernel-client.cjs');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const cases = [
  ['arithmetic', 'exact-rationals', '1/3 + 1/6 === 1/2'],
  ['arithmetic', 'complex', '(1+I)^2 === 2 I'],
  ['arithmetic', 'precision', 'Abs[N[Pi,40]-3.141592653589793238462643383279502884197] < 10^-38'],
  ['arithmetic', 'elementary-functions', 'Sin[Pi/6] === 1/2 && Log[E^3] === 3'],
  ['arithmetic', 'special-functions', 'Gamma[6] === 120 && BesselJ[0,0] === 1'],
  ['algebra', 'factor', 'Factor[x^4-1] === (x-1)(x+1)(x^2+1)'],
  ['algebra', 'factor-algebraic-extension', 'Factor[x^4+1,Extension->Sqrt[2]] === (x^2-Sqrt[2] x+1)(x^2+Sqrt[2] x+1)'],
  ['algebra', 'expand', 'Expand[(x+1)^3] === 1+3 x+3 x^2+x^3'],
  ['algebra', 'simplify', 'Simplify[Sin[x]^2+Cos[x]^2] === 1'],
  ['algebra', 'together', 'Together[1/x+1/(x+1)] === (1+2 x)/(x (1+x))'],
  ['algebra', 'polynomial-coefficients', 'CoefficientList[(x+1)^3,x] === {1,3,3,1}'],
  ['algebra', 'polynomial-division', 'PolynomialQuotient[x^3-1,x-1,x] === 1+x+x^2'],
  ['equations', 'solve', 'Sort[x /. Solve[x^2-5 x+6==0,x]] === {2,3}'],
  ['equations', 'linear-system', '({x,y} /. First[Solve[{x+y==3,x-y==1},{x,y}]]) === {2,1}'],
  ['equations', 'find-root', 'Abs[(x /. FindRoot[Cos[x]==x,{x,0.7}])-0.7390851332151607] < 10^-8'],
  ['equations', 'reduce', 'Reduce[x^2<1,x,Reals] === (-1<x<1)'],
  ['calculus', 'differentiate', 'D[Sin[x^2],x] === 2 x Cos[x^2]'],
  ['calculus', 'partial-derivative', 'D[x^2 y^3,x,y] === 6 x y^2'],
  ['calculus', 'integrate', 'Integrate[2 x,x] === x^2'],
  ['calculus', 'definite-integral', 'Integrate[Exp[-x^2],{x,-Infinity,Infinity}] === Sqrt[Pi]'],
  ['calculus', 'numerical-integral', 'Abs[NIntegrate[Sin[x],{x,0,Pi}]-2] < 10^-6'],
  ['calculus', 'limit', 'Limit[Sin[x]/x,x->0] === 1'],
  ['calculus', 'series', 'Normal[Series[Exp[x],{x,0,3}]] === 1+x+x^2/2+x^3/6'],
  ['calculus', 'sum', 'Sum[k,{k,1,100}] === 5050'],
  ['calculus', 'product', 'Product[k,{k,1,6}] === 720'],
  ['differential-equations', 'symbolic-ode', '(y[x] /. First[DSolve[y\'[x]==y[x],y[x],x]]) === C[1] Exp[x]'],
  ['differential-equations', 'numeric-ode', 'Head[NDSolve[{y\'[x]==y[x],y[0]==1},y,{x,0,1}]] === List'],
  ['linear-algebra', 'determinant', 'Det[{{1,2},{3,4}}] === -2'],
  ['linear-algebra', 'inverse', 'Inverse[{{1,2},{3,4}}] === {{-2,1},{3/2,-1/2}}'],
  ['linear-algebra', 'linear-solve', 'LinearSolve[{{2,1},{1,-1}},{5,1}] === {2,1}'],
  ['linear-algebra', 'eigenvalues', 'Sort[Eigenvalues[{{2,0},{0,3}}]] === {2,3}'],
  ['linear-algebra', 'matrix-rank', 'MatrixRank[{{1,2},{2,4}}] === 1'],
  ['linear-algebra', 'matrix-power', 'MatrixPower[{{1,1},{0,1}},3] === {{1,3},{0,1}}'],
  ['linear-algebra', 'dot', '{{1,2},{3,4}}.{5,6} === {17,39}'],
  ['linear-algebra', 'transpose', 'Transpose[{{1,2,3},{4,5,6}}] === {{1,4},{2,5},{3,6}}'],
  ['statistics', 'mean', 'Mean[{1,2,3,4}] === 5/2'],
  ['statistics', 'median', 'Median[{1,9,3}] === 3'],
  ['statistics', 'variance', 'Variance[{1,2,3}] === 1'],
  ['statistics', 'standard-deviation', 'StandardDeviation[{1,2,3}] === 1'],
  ['statistics', 'quantile', 'Quantile[{1,2,3,4},1/2] === 2'],
  ['statistics', 'normal-distribution', 'CDF[NormalDistribution[0,1],0] === 1/2'],
  ['number-theory', 'prime', 'Prime[100] === 541'],
  ['number-theory', 'prime-test', 'PrimeQ[104729]'],
  ['number-theory', 'integer-factorization', 'FactorInteger[360] === {{2,3},{3,2},{5,1}}'],
  ['number-theory', 'gcd', 'GCD[84,126] === 42'],
  ['number-theory', 'modular-power', 'PowerMod[2,10,17] === 4'],
  ['number-theory', 'integer-digits', 'FromDigits[IntegerDigits[2026,2],2] === 2026'],
  ['lists', 'table', 'Table[k^2,{k,1,4}] === {1,4,9,16}'],
  ['lists', 'map', 'Map[#^2&,{1,2,3}] === {1,4,9}'],
  ['lists', 'select', 'Select[Range[6],EvenQ] === {2,4,6}'],
  ['lists', 'fold', 'Fold[Plus,0,{1,2,3}] === 6'],
  ['lists', 'partition', 'Partition[Range[6],2] === {{1,2},{3,4},{5,6}}'],
  ['lists', 'association', '<|"a"->3,"b"->4|>["a"] === 3'],
  ['lists', 'sort', 'Sort[{3,1,2}] === {1,2,3}'],
  ['language', 'patterns', 'Cases[{a,2,b,3},_Integer] === {2,3}'],
  ['language', 'replace-all', '(x^2+y /. {x->2,y->3}) === 7'],
  ['language', 'local-scope', 'Module[{x=3},x^2] === 9'],
  ['language', 'pure-function', '(#1+#2&)[2,3] === 5'],
  ['language', 'condition', 'If[3>2,7,0] === 7'],
  ['language', 'recursion', 'Module[{f},f[0]=1;f[n_Integer]:=n f[n-1];f[6]] === 720'],
  ['strings', 'join', 'StringJoin["math","ematics"] === "mathematics"'],
  ['strings', 'replace', 'StringReplace["abcabc","ab"->"X"] === "XcXc"'],
  ['strings', 'regular-expression', 'StringCases["a12b34",RegularExpression["[0-9]+"]] === {"12","34"}'],
  ['strings', 'split', 'StringSplit["a,b,c",","] === {"a","b","c"}'],
  ['logic', 'boolean-simplification', 'BooleanMinimize[(a && b) || (a && !b)] === a'],
  ['optimization', 'minimize', 'First[Minimize[(x-2)^2,x]] === 0'],
  ['units', 'unit-conversion', 'QuantityMagnitude[UnitConvert[Quantity[1,"Kilometers"],"Meters"]] === 1000'],
  ['dates', 'leap-year', 'DateDifference[{2024,2,28},{2024,3,1},"Day"] === Quantity[2,"Days"]'],
  ['graphs', 'shortest-path', 'FindShortestPath[Graph[{1->2,2->3}],1,3] === {1,2,3}'],
];

(async () => {
  const command = process.env.MATHEMATICS_KERNEL || path.join(root, '.venv/bin/python');
  const args = process.env.MATHEMATICS_KERNEL ? [] : [path.join(root, 'backend/kernel.py')];
  const client = new KernelClient({command,args,cwd:root,timeoutMs:12000,startupMs:60000});
  const report = {schema:1,date:new Date().toISOString(),engine:'Mathics3 10.0.1',scope:'Representative examples only; this is not full Mathematica compatibility or a percentage of its functions.',cases:[]};
  try {
    await client.start();
    for (const [area,id,source] of cases) {
      const entry = {area,id,source,expected:'True'};
      try {
        const result = await client.request('evaluate',{source,notebook_id:'compatibility-catalog'});
        entry.actual = result.text;
        entry.messages = result.messages;
        entry.passed = result.text === 'True';
        entry.elapsed_ms = result.elapsed_ms;
      } catch(error) { entry.passed = false; entry.error = error.message; }
      report.cases.push(entry);
      if (!entry.passed) console.log(`GAP ${area}/${id}: ${(entry.actual || entry.error).slice(0,180)}`);
    }
  } finally { client.dispose(); }
  report.summary = {tested:report.cases.length,passed:report.cases.filter(x=>x.passed).length,gaps:report.cases.filter(x=>!x.passed).length};
  await fs.mkdir(path.join(root,'build'),{recursive:true});
  await fs.writeFile(path.join(root,'build/capability-results.json'),JSON.stringify(report,null,2)+'\n');
  if (process.argv.includes('--refresh-view')) {
    const view = path.join(root, 'renderer/compatibility.js');
    const source = await fs.readFile(view, 'utf8');
    if (!/^  const report = .*;$/m.test(source)) throw new Error('Capability view report placeholder is missing.');
    await fs.writeFile(view, source.replace(/^  const report = .*;$/m, () => '  const report = ' + JSON.stringify(report) + ';'));
  }
  console.log(JSON.stringify(report.summary));
})().catch(error => { console.error(error); process.exitCode=1; });
