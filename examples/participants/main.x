import util.Participant
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
    },
    210: {
      "name": "Ayesha",
      "gender":Gender.FEMALE,
      "age": 21,
      "foo": bar(),
      "array": [1, 2, 4, 5, 6],
    },
  }
}

const Participant partipants = getpartipants()

print(typeOf(partipants.200.array[0]));
print(partipants[200]);
