interface Person{
    string getGender()
}

class Animal implements Person{
    string getGender(){
        print("hello")
    }
}

let animal = new Animal();
print("getGender", animal.getGender())