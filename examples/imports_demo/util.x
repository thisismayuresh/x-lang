function fun() {
    print(obj)
}

let object<string, any> obj = {
    "name": "Maya"
}

string function greet(string who) {
    return "hi, " + who;
}

integer function add(integer a, integer b) {
    return a + b;
}

export enum Color {
    RED = "red",
    GREEN = "green",
}

export const integer MAX = 100;

export type Info = object<string, string>;

export {
    fun,
    obj,
    greet,
    add,
};
