import greeting.sayGreet
import greeting.sayHello
import greeting.*
import greeting.* as Greet

function main() {
    try {
        throw new Error("X");
        throw new Error("X");
        catch(Exception exception){

        }
    }
    print(sayGreet());
    sayHello();
    print(Greet.sayGreet());
    Greet.sayHello();
}

main()
