namespace Demo.Models {
    class User {
        public string name

        public User(string name) {
            this.name = name
        }
    }
}

class Container {
    class Entry {
        public string label

        public Entry(string label) {
            this.label = label
        }
    }
}

any function main() {
    let Demo.Models.User user = new Demo.Models.User("Ada")
    let Container.Entry entry = new Container.Entry("sample")

  
    print(user.name + " / " + entry.label)

    
}
