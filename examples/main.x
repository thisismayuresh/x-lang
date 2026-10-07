import System.io.FileSystem
let string[] entries = FileSystem.listDirectory("./");

for(int entry of entries ){
    //print(entry)
    if(entry==="main.x"){
        //print(FileSystem.readText(entry))
    }
}

any function myFunction(int i = 0) {
    if (i === 10) {
        return;
    }

    print(i);
    myFunction(i + 1);
}

myFunction(9);



let integer[] array = [5,4,3,2,1, getarrayAtZero(), getarrayAtZero(2)]



integer function getarrayAtZero(){
    return 1
}

integer function getarrayAtZero(int xp){
    return xp
}


print(`Value of is {array}`)




class Address {
    string street;
    string city;

    public Address(string street, string city) {
        this.street = street;
        this.city = city;
    }
}


public class UserAccount {
    // 1. Primitive and string fields
    private int userId;
    private string username;

    // 2. A custom object field (Composition)
    private Address billingAddress;

    // 3. An array field
    private int[] transactionHistory;

    // 4. Constructor to initialize the complex object
    public UserAccount(int userId, string username, Address billingAddress, int[] transactionHistory) {
        print("username", username);
        this.userId = userId;
        this.username = username;
        this.billingAddress = billingAddress;
        this.transactionHistory = transactionHistory;
    }

    // 5. Behavior (Method)
    public void printAccountDetails() {
        print("User: " + this.username + " (ID: " + this.userId + ")");
        print("City: " + this.billingAddress.city);
        //print("Recent Transactions: " + Arrays.tostring(transactionHistory));
    }
}



let Address userAddress = new Address("123 Java Lane", "Tech City");
let int[] history = [100, 250, 15]; 

let UserAccount account = new UserAccount(9876, "DevUser", userAddress, history);

account.printAccountDetails();

let obj = {
    "type": "us",
   
}

obj.x = "xxx";


print(obj.x);
print(obj)

interface Person{
    string getGender()
}

protected class ANimal implements Person{
  protected ANimal(){

    print("constr")
 }

 string getGender(){
    return "female"+" 1+1"
 }
}


let classm = new ANimal();

print("getgendr",classm.getGender())









 integer[] function foo(){
    let integer[] arrayo = [1];
    arrayo.push(2);
     return arrayo;
}

print("fooed", foo())


let nestedArray = [[1,2,3],[4,5,6],[7,8,9], [10]]
let nestedArray2 = [[1,2,3],[4,5,6],[7,8,9], [10]]


const leta3 = nestedArray[3][0]
typeOf(nestedArray[0]);
 const len=[].length===0
print(len)
print("hi")


let testArray = [];

if(testArray.length === 0){
    print("its working")
}
else{
    print("ummmmmmm")
}
print(false==0)





any function rest(int ...arguments){
    print("rest:",arguments);
return arguments
}

print("returned value-->"+rest(1,2,3,4,5,6,7,8,9,0))




let a = 10;

a > 100
    ? print("Greater than 100")
    : a > 50
        ? print("Greater than 50")
        : a > 5
            ? print("Greater than 5")
            : print("5 or less");



print(typeOf(print("Hi")))
print(typeOf("Hi"))
print(typeOf(1))
print(typeOf(print))



let sampleArray = [[1],1,2,3, "Hi"]
 sampleArray.pop()
  sampleArray.pop()
   //sampleArray.pop()
    //sampleArray.pop()
     //sampleArray.pop()

print(typeOf(sampleArray[0]))
for( let i in range(1,sampleArray.length)) {
  //  sampleArray.pop()
  print(sampleArray[1])

print("typeOf",typeOf(i))
}

let int age = input(" enter age")

print("age is",age)