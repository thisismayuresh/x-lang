import util.MyNamespace.*
import util.MyNamespace.greet as sayHi
import util

string function hello() {
  return "hello world";
}

// print(hello() + obj);

function funs() {
  print(fun())
  print(greet("Ada"))
  print(add(2, 3))
  print(Color.RED)
  print(sayHi("Bo"))
  print(util.MyNamespace.add(10, 32))
  print(util.MAX)
}

funs()
