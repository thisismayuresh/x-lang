abstract class Animal {
    private string name;

    public Animal(string name) {
        this.name = name;
    }

    public string getName() {
        return this.name;
    }

    public abstract string speak();
}

class Dog extends Animal {
    public Dog(string name) {
        super(name);
    }

    public override string speak() {
        return super.getName() + " says woof";
    }
}

function main() {
    let Animal dog = new Dog("Rex");

    let integer[] array = [1, 2, 3, 4, 5];

   
     for (integer i in range(0, 10, 1)) {
        print("Hello "+i);
        print (array);

     }
    print("Hello World");
    print(dog.speak());
}
