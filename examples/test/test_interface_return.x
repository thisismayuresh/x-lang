interface Person{
    string getGender()
}

class Animal implements Person{
    string getGender(){
        return 1
    }
}

let animal = new Animal();
print("getGender", animal.getGender())