class Address {
    string street;
    string city;

    public string Address(string street, string city) {
        this.street = street;
        this.city = city;
    }
}

let Address addr = new Address("123 Main St", "New York")
print(addr)