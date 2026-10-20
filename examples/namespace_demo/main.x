import util.MyNamespace.fun
import util.MyNamespace.greet
import util.MyNamespace.add
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
    print(sayHi("Bo"))
    print(util.MyNamespace.add(10, 32))
    print(util.MAX)
}


funs()
