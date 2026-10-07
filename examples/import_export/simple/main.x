import greeting.sayGreet
import greeting.sayHello
import greeting.*
import greeting.* as Greet


any function test(){
    print("Hello-----------------");
}

any function main() {
    print(1+1+2);
  try {
    // Code that might throw an exception
    let integer data = 50/0; 
} catch (Exception e) {
    // Code to handle the exception
    print("Cannot divide by zero: " + e);
}

    sleep(8000)

    print(sayGreet());
    sayHello();
    print(Greet.sayGreet());
    Greet.sayHello();

     let string name = "Maya";
    let integer count = 3;

    print("My Name " + "is", "Maya");
    print("My Name " + "is", name);
    print(`Hello {name}. 2 + 1 = {2 + 1}.`);
    print(`Hello {test()}. 2 + 1 = {2 + 1}.`);
    print(`This template spans
multiple lines, and still interpolates {count}.`);
    print(`Use {{ and }} to show braces without interpolation.`);
    print("Arrays:", [1, 2, 3], "objects:", {active: true});

    let object[] profile = [{
        "name": "Maya",
        age: "21"
}]

   //print(`Hello {profile.name} {typeOf(4/2)}`);

    print("Null/null:", typeOf(Null), typeOf(null));
    print("Undefined/undefined:", typeOf(Undefined), typeOf(undefined));
    print("Missing profile field:", typeOf(profile[0]?.x), profile[0]?.x);

}
main()
