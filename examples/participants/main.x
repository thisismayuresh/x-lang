import util.Participant
import util.Participants
import util.Gender
import util.bar


Participant function getpartipants() {
  return {
    200: {
      "name": "Maya",
      "gender":Gender.FEMALE,
      "age": 21,
      "foo": bar(),
      "array": [1, 2, 4, 5, 6],
      "isMarried": false,
    },
    210: {
      "name": "Ayesha",
      "gender":Gender.FEMALE,
      "age": 21,
      "foo": bar(),
      "array": [1, 2, 4, 5, 6],
      "isMarried": false,
    },
  }
}

const Participant partipants = getpartipants()

print(typeOf(partipants.200.array[0]));
print(partipants[200]);

Participants function getRegistrations() {
  return {
    300: {
      "name": "Rahul",
      "gender": Gender.MALE,
      "age": 24,
      "foo": bar(),
      "array": [7, 8],
      "isMarried": false,
    },
    310: {
      "name": "Zoya",
      "gender": Gender.FEMALE,
      "age": 22,
      "foo": bar(),
      "array": [9],
      "isMarried": false,
    },
  }
}

const Participants registrations = getRegistrations()
print(typeOf(registrations));
print(registrations.300.name);
