import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from xlang.lexer import Lexer
from xlang.module_loader import ModuleLoader
from xlang.parser import Parser
from xlang.runtime import Interpreter, RuntimeErrorX


class InterpreterTests(unittest.TestCase):
    def run_x(self, source, arguments=None):
        output = []
        program = Parser(Lexer(source).tokenize()).parse()
        result = Interpreter(arguments, output.append).interpret(program)
        return result, output

    def test_function_calls_and_string_concatenation(self):
        result, output = self.run_x(
            """
            string function greet(string name) {
                return "Hello " + name;
            }
            function main() {
                print(greet("Ada"));
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["Hello Ada"])

    def test_for_loop_range_and_command_line_arguments(self):
        result, output = self.run_x(
            """
            integer function main(string[] args) {
                for (integer value in range(0, 3, 1)) {
                    print(args[0] + value);
                }
                return 7;
            }
            """,
            ["item"],
        )
        self.assertEqual(result, 7)
        self.assertEqual(output, ["item0", "item1", "item2"])

    def test_classes_overloaded_constructors_and_methods(self):
        result, output = self.run_x(
            """
            class User {
                private string name;
                public User(integer id) {
                    this.name = "user" + id;
                }
                public User(string name) {
                    this.name = name;
                }
                public string greet() {
                    return "Hello " + this.name;
                }
            }
            function main() {
                let User user = User("Ada");
                print(user.greet());
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["Hello Ada"])

    def test_inheritance_and_super_constructor(self):
        result, output = self.run_x(
            """
            class Animal {
                private string name;
                public Animal(string name) {
                    this.name = name;
                }
                public string speak() {
                    return this.name;
                }
            }
            class Dog extends Animal {
                public Dog(string name) {
                    super(name);
                }
                public string speak() {
                    return super.speak() + " says woof";
                }
            }
            function main() {
                print(Dog("Rex").speak());
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["Rex says woof"])

    def test_generic_class_and_function_syntax(self):
        result, output = self.run_x(
            """
            class Box<T> {
                private T value;
                public Box(T value) {
                    this.value = value;
                }
                public T get() {
                    return this.value;
                }
            }
            function<T> T identity(T value) {
                return value;
            }
            function main() {
                let Box<string> box = Box<string>("hello");
                print(identity<string>(box.get()));
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["hello"])

    def test_static_fields_and_methods(self):
        result, output = self.run_x(
            """
            class Counter {
                public static integer count = 0;
                public static integer next() {
                    Counter.count++;
                    return Counter.count;
                }
            }
            function main() {
                print(Counter.next());
                print(Counter.count);
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["1", "1"])

    def test_new_exception_and_catch(self):
        result, output = self.run_x(
            """
            function main() {
                try {
                    throw new Exception("expected");
                }
                catch (Exception error) {
                    print(error.message);
                }
            }
            """
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["expected"])

    def test_grouped_import_with_alias(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_directory = project_root / "demo"
            module_directory.mkdir()
            module_file = module_directory / "Greeter.x"
            module_file.write_text(
                """
                export class Greeter {
                    public string greet() {
                        return "hello";
                    }
                }
                """,
                encoding="utf-8",
            )
            entry_file = project_root / "main.x"
            entry_file.write_text(
                """
                import demo.{Greeter as Friendly}
                function main() {
                    let Friendly greeter = Friendly();
                    print(greeter.greet());
                }
                """,
                encoding="utf-8",
            )

            program = ModuleLoader(project_root).load_program(entry_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["hello"])

    def test_filesystem_standard_library_import(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            entry_file = project_root / "main.x"
            entry_file.write_text(
                """
                import System.io.FileSystem
                function main(string[] args) {
                    let string directory = args[0];
                    let string filePath = directory + "/sample.txt";
                    FileSystem.createDirectory(directory);
                    FileSystem.writeText(filePath, "first");
                    FileSystem.appendText(filePath, " second");
                    print(FileSystem.isDirectory(directory));
                    print(FileSystem.readText(filePath));
                    let string[] entries = FileSystem.listDirectory(directory);
                    for (string entry in entries) {
                        print(entry);
                    }
                    FileSystem.deleteFile(filePath);
                    print(FileSystem.exists(filePath));
                    FileSystem.deleteDirectory(directory);
                }
                """,
                encoding="utf-8",
            )
            directory = project_root / "output"
            program = ModuleLoader(project_root).load_program(entry_file)
            output = []
            result = Interpreter([str(directory)], output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(
            output,
            ["true", "first second", "sample.txt", "false"],
        )
        self.assertFalse(directory.exists())

    def test_filesystem_read_errors_are_reported(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            entry_file = project_root / "main.x"
            entry_file.write_text(
                """
                import System.io.FileSystem
                function main(string[] args) {
                    FileSystem.readText(args[0]);
                }
                """,
                encoding="utf-8",
            )
            missing_path = str(project_root / "missing.txt")
            program = ModuleLoader(project_root).load_program(entry_file)

            with self.assertRaisesRegex(RuntimeErrorX, "Cannot read text file"):
                Interpreter([missing_path]).interpret(program)

    def test_constants_cannot_be_reassigned(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Cannot reassign constant"):
            self.run_x(
                """
                function main() {
                    const integer limit = 2;
                    limit = 3;
                }
                """
            )


if __name__ == "__main__":
    unittest.main()
