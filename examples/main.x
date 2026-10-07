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

        return "Hello"
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
        this.transactionHistory = transactionHistory
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

//let int age = input("Enter age: ", "integer")
//age=7
//print("age is",age)



void function ac(int ab=10){
    print(ab)
}

print("ACCCC"+ac(99))




let arrayToBeMapped = [1,2,3,4,5,6];

/*
arrayToBeMapped.map(int a=>{
    print(a)
})

*/

  class X{
    public X(){
        print("Constructor called")
    }
}

print("Type of clas is:"+typeOf(X))

interface Bar{
    void stringP()
}
interface Foo extends Bar{
    int P(string x),

}

class D extends X implements Foo{
    public static any Secreat = "X";
    public int P(string x) {
        sayHello(this)
        return x.length

    }
    public  static void stringP() {
        print("stringP called")
    }
}

any function sayHello(any variable){
    print("VARIABLE",variable)
}

print("typeof", typeOf(Bar))

print("Hi", D.P("aeiou"+"hello".length))

print("hello".length)

print(typeOf(5+6))

print(D.Secreat);


// ============================================================
// COMPLEX INTERFACE INHERITANCE - "RABBIT HOLE" EXAMPLES
// ============================================================

// Base interfaces
interface Printable {
    void print();
}

interface Serializable {
    string serialize();
}

interface Comparable {
    int compareTo(any other);
}

// Interface extending single interface (multiple not supported yet)
interface Storable extends Serializable {
    void save();
}

interface Queryable {
    any find(string query);
}

// Deep interface hierarchy
interface A {
    void methodA();
}

interface B extends A {
    void methodB();
}

interface C extends B {
    void methodC();
}

interface Dogge extends C {
    void methodD();
}

// Class implementing deep hierarchy + Queryable
class DeepImpl implements D, Queryable {
    public void methodA() { print("A") }
    public void methodB() { print("B") }
    public void methodC() { print("C") }
    public void methodD() { print("D") }
    public any find(string query) { 
        print("Finding: " + query);
        return {found: true, query: query};
    }
}

// Multiple interface implementation
interface Runnable {
    void run();
}

interface Stoppable {
    void stop();
}

interface Pausable {
    void pause();
}

class Task implements Runnable, Stoppable, Pausable {
    private string name;
    
    public Task(string name) {
        this.name = name;

     
    }
    
    public void run() { print(this.name + " running"); }
    public void stop() { print(this.name + " stopped"); }
    public void pause() { print(this.name + " paused"); }
}

// Interface with static fields (constants) - these are NOT inherited by implementing classes
interface Config {
    // Static constants - not part of interface contract
    static int MAX_RETRIES = 3;
    static string DEFAULT_URL = "http://localhost";
}

class AppConfig {
    // Not implementing Config since static fields aren't part of interface contract
}

// Test the complex interfaces
print("=== Testing Complex Interface Hierarchy ===");

let DeepImpl deep = new DeepImpl();
deep.methodA();
deep.methodB();
deep.methodC();
deep.methodD();

print("");

let Task task = new Task("MyTask");
task.run();
task.pause();
task.stop();

print("");

// Test interface constants
print("Config MAX_RETRIES: " + Config.MAX_RETRIES);
print("Config DEFAULT_URL: " + Config.DEFAULT_URL);

// Interface as type annotation
let Queryable q = deep;
print("Queryable assigned from DeepImpl: " + typeOf(q));

print("=== Complex Interface Tests Complete ===");