export namespace MyNamespace {
  function fun() {
    print(obj)
  }

  let object < string, any > obj = { "name": "Maya" }

  string function greet(string who) {
    return "hi, " + who;
  }

  integer function add(integer a, integer b) {
    return a + b;
  }

  enum Color {
    RED = "red", GREEN = "green",
  }

  enum Gender {
    FEMALE = "female", MALE = "male",
  }

  let object<string, string|Gender> object = {
        "name": "Maya",
        "age": "21",
        "gender": Gender.FEMALE
    }
}

export const integer MAX = 100;

export type Info = object < string, any >;
