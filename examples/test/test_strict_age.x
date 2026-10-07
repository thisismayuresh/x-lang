import System.io.Console

Console.print("=== Strict Typing Age Input Test ===")

Console.print("\nTest 1: Valid integer input")
let int age = Console.input("Enter your age: ", "int")
Console.print("Age is:", age, "type:", typeOf(age))

Console.print("\nTest 2: Valid float input")
let float height = Console.input("Enter your height: ", "float")
Console.print("Height is:", height, "type:", typeOf(height))

Console.print("\nTest 3: Valid boolean input")
let boolean isStudent = Console.input("Are you a student? (true/false): ", "bool")
Console.print("Is student:", isStudent, "type:", typeOf(isStudent))

Console.print("\nTest 4: Valid string input")
let string name = Console.input("Enter your name: ", "string")
Console.print("Name is:", name, "type:", typeOf(name))

Console.print("\n=== All tests completed ===")