export void function testExport (){
    print("hello");

}


void function mutate(Payment object){

    object.accountBalance = 0
}


class Payment{
    public int accountBalance = 100

     void test(){
        mutate(this)
    }
}


let Payment payment =  new Payment()
print(payment.accountBalance)

payment.test()

print(payment.accountBalance)


export {
    mutate
};