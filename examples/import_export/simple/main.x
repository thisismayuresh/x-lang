import greeting.sayGreet
import greeting.sayHello
import greeting.*
import greeting.* as Greet

function main() {
    print(1+1+2);
  try {
    // Code that might throw an exception
    let integer data = 50/0; 
} catch (Exception e) {
    // Code to handle the exception
    print("Cannot divide by zero: " + e);
}
    print(sayGreet());
    sayHello();
    print(Greet.sayGreet());
    Greet.sayHello();
}

main()
