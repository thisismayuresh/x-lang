class Address {
    string street;
    string city;

    public Address(string street, string city) {
        this.street = street;
        this.city = city;

        return "hello"
    }
}

let Address addr = new Address("123 Main St", "New York")
print(addr)