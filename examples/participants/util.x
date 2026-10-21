// Shared types for the Participants registration maps:
// - Participant: a map interface — participant id (integer) → fields
//   (name/gender/age/foo/array/isMarried; age may be an int or a string,
//   gender is a Gender enum value, array is an integer list). Declared as
//   `integer key { ... }`, so the literal is checked key by key.
// - ParticipantList: the same shape as an array of objects
//   (`IParticipantValue[]`) for ordered, non-keyed access.
// - Participants: ultra-nested id → field name → value, where each value
//   spans the union of every field type (kept as an object<K, V> alias,
//   since the value's field names are open).



export enum Gender {
  MALE = "Male",
  FEMALE = "Female",
}

export interface Participant {
  integer key {
    string name,
    Gender gender,
    number age,
    any? foo,
    integer[] array,
    boolean isMarried,
  }
}

// The same value shape spelled as an element type, for code that wants an
// ordered list instead of an id-keyed map (fields mirror Participant above).
export interface IParticipantValue {
  string name,
  Gender gender,
  number age,
  any? foo,
  integer[] array,
  boolean isMarried,
}

export type ParticipantList = IParticipantValue[]

// Ultra-nested registration shape: participant id → field name → value,
// where each value spans the union of every field type.
export type Participants = Object<integer, Object<string, string|integer|Gender|integer[]|boolean>>


/*
Type Script Specific (what `x compile --target typescript` now emits
for the map interface above):

interface Participant {
  [key: number]: { name: string; gender: Gender; age: number; foo: any; array: number[]; isMarried: boolean };
}

*/



export string function bar(){
  return "bar"
}


class SomeClass{
  private object data = {"hi":"hello"}
  SomeClass(string a, string b){
    
  }

  static void getData(){
      let object data = {"hi":"hello"}

    print(data)
  }
}

print(SomeClass.getData())

