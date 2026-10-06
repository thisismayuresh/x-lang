import System.io.FileSystem
let string[] entries = FileSystem.listDirectory("./");

for(int entry of entries ){
    //print(entry)
    if(entry==="main.x"){
        //print(FileSystem.readText(entry))
    }
}

function myFunction(intsssssx i = 0) {
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

integer function getarrayAtZero(xp){
    return xp
}


print(`Value of is {array}`)




class Address {
    string street;
    string city;

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }
}


public class UserAccount {
    // 1. Primitive and String fields
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
        //print("Recent Transactions: " + Arrays.toString(transactionHistory));
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
}


let classm = new ANimal();









 function foo(){
    let integer[] arrayo = [1];
    arrayo.push(2);
     return arrayo;
}

print("fooed",             foo())



