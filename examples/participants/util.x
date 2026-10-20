// Shared type for the Participants registration map:
// participant id (integer) → fields (name/gender/age/foo/array/isMarried; age
// may be an int or a string, gender is either a plain string or a Gender enum
// value, array is an integer list).



export enum Gender {
  MALE = "Male",
  FEMALE = "Female",
}

interface IParticipantValue {
  string name,
  Gender gender,
  number age,
  any? foo,
  integer[] array,
  boolean isMarried,
}

export type Participant = Object<integer, IParticipantValue>

// Ultra-nested registration shape: participant id → field name → value,
// where each value spans the union of every field type.
export type Participants = Object<integer, Object<string, string|integer|Gender|integer[]|boolean>>


/*
Type Script Specific 

interface Participant {
  name: string;
  gender: string;
  age: number;
  foo?: unknown;
  array?: number[];
  isMarried?: boolean;
}

interface Participants {
  [id: number]: Participant;
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

