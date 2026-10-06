import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from xlang.lexer import LexError
from xlang.module_loader import ModuleLoader
from xlang.parser import ParseError
from xlang.runtime import Interpreter, RuntimeErrorX


class InterpreterTests(unittest.TestCase):
    def run_x(self, source, arguments=None, environment=None):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text(source, encoding="utf-8")
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter(
                arguments, output.append, environment=environment
            ).interpret(program)
        return result, output

    def test_function_calls_and_string_concatenation(self):
        result, output = self.run_x("""
            string function greet(string name) {
                return "Hello " + name;
            }
            function main() {
                print(greet("Ada"));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Hello Ada"])

    def test_type_of_reports_javascript_style_type_names(self):
        result, output = self.run_x("""
            function greet() {}
            class User {}
            enum Status { READY }
            function main() {
                let object value = {
                    "name": "Maya",
                    age: 21
                };
                print(typeOf(value));
                print(typeOf(value.name));
                print(typeOf(value.age));
                print(typeOf(1.5));
                print(typeOf(true));
                print(typeOf(null));
                print(typeOf([1, 2]));
                print(typeOf(greet));
                print(typeOf(User));
                print(typeOf(Status.READY));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "object",
                "string",
                "number",
                "number",
                "boolean",
                "object",
                "Array",
                "function",
                "function",
                "object",
            ],
        )

    def test_generic_object_type_validates_key_and_value_shapes(self):
        result, output = self.run_x("""
            function main() {
                let object<string, string> user = {
                    "name": "Maya",
                    "age": "21",
                    "gender": "Rather not to say"
                };
                print(typeOf(user));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["object"])

        with self.assertRaisesRegex(
            RuntimeErrorX, "Expected 'string'.*object value at key 'age'"
        ):
            self.run_x("""
                function main() {
                    let object<string, string> user = {
                        "name": "Maya",
                        "age": 21
                    };
                }
                """)

        with self.assertRaisesRegex(
            RuntimeErrorX, "Expected 'string'.*object value at key 'age'"
        ):
            self.run_x("""
                function main() {
                    let object<string, string> user = {"age": "21"};
                    user = {"age": 21};
                }
                """)

        with self.assertRaisesRegex(
            RuntimeErrorX, "Expected 'string'.*object value at key 'age'"
        ):
            self.run_x("""
                function main() {
                    let object<string, string> user = {"age": "21"};
                    user.age = 21;
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "No overload of 'update' matches"):
            self.run_x("""
                function update(object<string, string> user) {}
                function main() {
                    update({"age": 21});
                }
                """)

    def test_callback_function_types_and_structural_interfaces(self):
        result, output = self.run_x("""
            interface Data {
                string name,
            }
            export interface IMyInterface {
                string getMessage(string message),
                Data [] getData(int id),
                Data primary,
                Data[] records,
                Function onComplete,
            }
            string function makeMessage() {
                return "finished";
            }
            string function getMessage(string message) {
                return "Hello " + message;
            }
            Data[] function getData(int id) {
                return [{name: "item " + id}];
            }
            string function runCallback(Function callback) {
                return callback();
            }
            class Service implements IMyInterface {
                Data primary = {name: "class primary"};
                Data[] records = [{name: "class cached"}];
                Function onComplete = makeMessage;
                string getMessage(string message) {
                    return "Service " + message;
                }
                Data[] getData(int id) {
                    return [{name: "service " + id}];
                }
            }
            function main() {
                let IMyInterface service = {
                    getMessage: getMessage,
                    getData: getData,
                    primary: {name: "primary"},
                    records: [{name: "cached"}],
                    onComplete: makeMessage
                };
                let IMyInterface classService = new Service();
                let Function callback = service.onComplete;
                let function lowerCaseCallback = makeMessage;
                let Data[] records = service.getData(1);
                print(service.getMessage("Maya"));
                print(records[0].name);
                print(service.primary.name, service.records[0].name);
                print(classService.getMessage("Maya"), classService.primary.name);
                print(runCallback(callback), runCallback(lowerCaseCallback));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "Hello Maya",
                "item 1",
                "primary cached",
                "Service Maya class primary",
                "finished finished",
            ],
        )

    def test_function_and_interface_types_reject_mismatched_values(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'Function'"):
            self.run_x("""
                function main() {
                    let Function callback = 42;
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'Profile'"):
            self.run_x("""
                interface Profile {
                    string name,
                }
                function main() {
                    let Profile user = {name: 21};
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'IMyInterface'"):
            self.run_x("""
                interface Data { string name, }
                interface IMyInterface {
                    string getMessage(string message),
                    Data[] getData(int id),
                }
                integer function wrongMessage(int value) { return value; }
                Data[] function getData(int id) { return []; }
                function main() {
                    let IMyInterface service = {
                        getMessage: wrongMessage,
                        getData: getData
                    };
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'Profile'"):
            self.run_x("""
                interface Profile {
                    string name,
                }
                function main() {
                    let Profile[] users = [{name: 21}];
                }
                """)

    def test_type_of_requires_exactly_one_argument(self):
        with self.assertRaisesRegex(RuntimeErrorX, "typeOf expects one argument"):
            self.run_x("function main() { typeOf(); }")

        with self.assertRaisesRegex(RuntimeErrorX, "typeOf expects one argument"):
            self.run_x("function main() { typeOf(1, 2); }")

    def test_null_and_undefined_literals_are_object_typed_and_distinct_values(self):
        result, output = self.run_x("""
            function main() {
                let empty = {};
                let profile = [{name: "Maya"}];
                print(typeOf(null), typeOf(Null));
                print(typeOf(undefined), typeOf(Undefined));
                print(null === Null, undefined === Undefined);
                print(null == undefined);
                print(null, undefined);
                print(typeOf(empty?.missing), empty?.missing);
                print(typeOf(profile[0]?.x), profile[0]?.x);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "object object",
                "object object",
                "true true",
                "true",
                "null undefined",
                "object undefined",
                "object undefined",
            ],
        )

    def test_object_can_be_an_inferred_variable_name_or_a_type(self):
        result, output = self.run_x("""
            function main() {
                let object = {name: "Maya"};
                let object profile = {name: "Grace"};
                print(object.name);
                print(profile.name);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Maya", "Grace"])

    def test_nested_functions_are_declared_without_running_and_capture_locals(self):
        result, output = self.run_x("""
            function main() {
                let integer count = 0;
                print("before declaration");
                string function greet(string name) {
                    count++;
                    return "Hello " + name;
                }
                print("after declaration");
                print(count);
                print(greet("Maya"));
                print(count);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            ["before declaration", "after declaration", "0", "Hello Maya", "1"],
        )

    def test_nested_function_can_be_declared_in_a_block_and_called_later(self):
        result, output = self.run_x("""
            function main() {
                if (true) {
                    function add(integer left, integer right) {
                        return left + right;
                    }
                    print(add(2, 3));
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["5"])

    def test_optional_chaining_handles_null_missing_and_out_of_range_values(self):
        result, output = self.run_x("""
            function greet(string name) {
                return "Hello " + name;
            }
            function main() {
                let users = ["Alice", "Bob"];
                let profile = [{x: "present"}];
                let object[] typedProfiles = [{name: "Maya"}];
                let user = {profile: {getName: greet}};
                let account = {};
                let missing = null;
                let callback = null;
                let integer argumentEvaluations = 0;

                print(users?[0]);
                print(typeOf(users?[5]));
                print(profile?[0]?.x);
                print(typeOf(typedProfiles[0]?.x));
                print(typeOf(profile[0]?.missing));
                print(typeOf(missing?.profile?.name));
                print(typeOf(missing?[0]?.x));
                print(typeOf(missing?.getName?.()));
                print(typeOf(account?.missing));
                print(typeOf(callback?.(argumentEvaluations++)));
                print(typeOf(missing?[argumentEvaluations++]));
                print(argumentEvaluations);
                print(greet?.("Maya"));
                print(user?.profile?.getName?.("Grace"));
                print(({profile: {getName: greet}}).profile?.getName?.("Ada"));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "Alice",
                "object",
                "present",
                "object",
                "object",
                "object",
                "object",
                "object",
                "object",
                "object",
                "object",
                "0",
                "Hello Maya",
                "Hello Grace",
                "Hello Ada",
            ],
        )

    def test_optional_access_coexists_with_ternary_expressions(self):
        result, output = self.run_x("""
            function main() {
                let users = ["Alice", "Bob"];
                let first = true ? users?[0] : "no user";
                let second = false ? users?[0] : users?[5];
                let values = true ? [1, 2] : [];
                print(first);
                print(typeOf(second));
                print(typeOf(values));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Alice", "object", "Array"])

    def test_regular_access_still_errors_for_invalid_indexes(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Cannot access index 5"):
            self.run_x("""
                function main() {
                    let users = ["Alice"];
                    print(users[5]);
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Cannot access index"):
            self.run_x("""
                function main() {
                    let users = ["Alice"];
                    print(users?["name"]);
                }
                """)

    def test_multiline_templates_interpolate_expressions_and_run_calls(self):
        result, output = self.run_x("""
            enum Status { READY }
            class User {
                public string name;
                public User(string name) { this.name = name; }
            }
            let integer counter = 0;
            string function nextName() {
                counter++;
                return "Maya";
            }
            function main() {
                let string name = "Ada";
                let User user = new User("Grace");
                let object profile = {name: name, status: Status.READY};
                print("My Name " + "is", "Maya");
                print(`My Name ` + `is`, name);
                print(`Hello {name}, {1 + 2}, {user.name}, {Status.READY}`);
                print(`escaped {{name}} and {profile}`);
                print(`line one
line two {name}
line three`);
                print(`first {nextName()} then {nextName()} count={counter}`);
                print("comma", name + "!", [1, 2], {active: true}, null);
                print(``);
                print();
            }
            """)

        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "My Name is Maya",
                "My Name is Ada",
                "Hello Ada, 3, Grace, READY",
                "escaped {name} and {name: Ada, status: READY}",
                "line one\nline two Ada\nline three",
                "first Maya then Maya count=2",
                "comma Ada! [1, 2] {active: true} null",
                "",
                "",
            ],
        )

    def test_template_interpolation_reports_empty_and_unterminated_expressions(self):
        with self.assertRaisesRegex(ParseError, "interpolation cannot be empty"):
            self.run_x("function main() { print(`bad {}`); }")

        with self.assertRaisesRegex(ParseError, "Unterminated template interpolation"):
            self.run_x("function main() { print(`bad {1 + 2`); }")

    def test_unterminated_multiline_template_is_a_lexer_error(self):
        with self.assertRaisesRegex(LexError, "Unterminated template literal"):
            self.run_x("function main() { print(`unfinished); }")

    def test_default_and_nullable_parameters_can_be_omitted(self):
        result, output = self.run_x("""
            class User {
                public string id;
                public User(string id) {
                    this.id = id;
                }
            }
            User function getUsers(string id = "10001") {
                return User(id);
            }
            User? function getOptionalId(string? id) {
                if (id == null) {
                    return null;
                }
                return User(id);
            }
            integer function addOffset(integer value, integer offset = value + 1) {
                return value + offset;
            }
            function main() {
                print(getUsers().id);
                print(getUsers("20002").id);
                print(getOptionalId() == null);
                print(getOptionalId(null) == null);
                print(getOptionalId("30003").id);
                print(addOffset(4));
                print(addOffset(4, 10));
                try {
                    throw new DatabaseError("unknown database failure");
                }
                catch (Throwable error) {
                    print(error.name);
                }
            }
            """)

        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "10001",
                "20002",
                "true",
                "true",
                "30003",
                "9",
                "14",
                "DatabaseError",
            ],
        )

    def test_required_parameter_cannot_follow_optional_parameter(self):
        with self.assertRaisesRegex(
            ParseError, "Required parameters cannot follow optional parameters"
        ):
            self.run_x("""
                function invalid(string? optional, string required) {}
                """)

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
        result, output = self.run_x("""
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
                let User user = new User("Ada");
                print(user.greet());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Hello Ada"])

    def test_inheritance_and_super_constructor(self):
        result, output = self.run_x("""
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
                print(new Dog("Rex").speak());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Rex says woof"])

    def test_class_can_extend_a_deeply_nested_class(self):
        result, output = self.run_x("""
            class Outer {
                class Middle {
                    class Deep {
                        class Base {
                            public string identify() { return "nested base"; }
                        }
                    }
                }
            }
            class Child extends Outer.Middle.Deep.Base {}
            function main() {
                let Outer.Middle.Deep.Base value = new Child();
                print(value.identify());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["nested base"])

    def test_generic_class_and_function_syntax(self):
        result, output = self.run_x("""
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
                let Box<string> box = new Box<string>("hello");
                print(identity<string>(box.get()));
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["hello"])

    def test_static_fields_and_methods(self):
        result, output = self.run_x("""
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
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["1", "1"])

    def test_new_exception_and_catch(self):
        result, output = self.run_x("""
            function main() {
                try {
                    throw new Exception("expected");
                }
                catch (Exception error) {
                    print(error.message);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["expected"])

    def test_exception_hierarchy_catches_runtime_and_domain_errors(self):
        result, output = self.run_x("""
            function main() {
                try {
                    let integer value = 1 / 0;
                }
                catch (ArithmeticException error) {
                    print(error.name + ": " + error.message);
                    print(error.stack != "");
                }
                catch (Throwable error) {
                    print("fallback");
                }

                try {
                    let int[] invalidValues = [1, "bad"];
                }
                catch (TypeException error) {
                    print(error.name);
                }

                try {
                    throw new DatabaseException(
                        "query failed",
                        new IOException("connection unavailable")
                    );
                }
                catch (Exception error) {
                    print(error.name + ": " + error.message);
                    print(error.cause.message);
                }

                try {
                    throw new DatabaseError("database invariant failed");
                }
                catch (Error error) {
                    print(error.name);
                }
            }
            """)

        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "ArithmeticException: Division by zero for '/'",
                "true",
                "TypeException",
                "DatabaseException: query failed",
                "connection unavailable",
                "DatabaseError",
            ],
        )

    def test_custom_exception_classes_support_inheritance_and_super(self):
        result, output = self.run_x("""
            class CustomException extends Exception {
                public integer statusCode;
                public CustomException(string message, integer statusCode) {
                    super(message);
                    this.statusCode = statusCode;
                }
            }
            class BadRequestException extends CustomException {
                public BadRequestException(string message) {
                    super(message, 400);
                }
            }
            class SimpleException extends Exception {}

            function main() {
                try {
                    throw new BadRequestException("invalid user id");
                }
                catch (CustomException error) {
                    print(error.name + ": " + error.message);
                    print(error.statusCode);
                    print(error.stack != "");
                }

                try {
                    throw new SimpleException("simple custom error");
                }
                catch (Exception error) {
                    print(error.name + ": " + error.message);
                }
            }
            """)

        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "BadRequestException: invalid user id",
                "400",
                "true",
                "SimpleException: simple custom error",
            ],
        )

    def test_file_system_failures_are_catchable_as_io_or_file_system_errors(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            source_file.write_text(
                """
                import System.io.FileSystem
                function main(string[] args) {
                    try {
                        FileSystem.readText(args[0]);
                    }
                    catch (IOException error) {
                        print(error.name);
                        print(error.stack != "");
                    }
                }
                """,
                encoding="utf-8",
            )
            missing_file = str(project_root / "not-found.txt")
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter([missing_file], output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["FileSystemException", "true"])

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

    def test_relative_module_import_and_top_level_function_call(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            example_directory = project_root / "control_flow"
            example_directory.mkdir()
            module_file = example_directory / "main.x"
            module_file.write_text(
                """
                export function main() {
                    print("exported main called");
                }
                """,
                encoding="utf-8",
            )
            entry_file = example_directory / "runner.x"
            entry_file.write_text(
                """
                import main
                main()
                """,
                encoding="utf-8",
            )
            program = ModuleLoader(project_root).load_program(entry_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["exported main called"])

    def test_import_executes_exported_module_top_level_call_once(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            example_directory = project_root / "control_flow"
            example_directory.mkdir()
            module_file = example_directory / "main.x"
            module_file.write_text(
                """
                export function main() {
                    print("main called by its module");
                }
                main()
                """,
                encoding="utf-8",
            )
            entry_file = example_directory / "runner.x"
            entry_file.write_text(
                """
                import main
                """,
                encoding="utf-8",
            )
            program = ModuleLoader(project_root).load_program(entry_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["main called by its module"])

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

    def test_async_filesystem_operations_and_millisecond_sleep(self):
        with TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            source_file = project_root / "main.x"
            file_path = project_root / "async.txt"
            source_file.write_text(
                f"""
                import System.io.FileSystem
                async function main() {{
                    await FileSystem.writeTextAsync("{file_path}", "first");
                    await FileSystem.appendTextAsync("{file_path}", " second");
                    let string contents = await FileSystem.readTextAsync("{file_path}");
                    await sleep(1);
                    print(contents);
                    print(await FileSystem.existsAsync("{file_path}"));
                    await FileSystem.deleteFileAsync("{file_path}");
                }}
                """,
                encoding="utf-8",
            )
            program = ModuleLoader(project_root).load_program(source_file)
            output = []
            result = Interpreter(output=output.append).interpret(program)

        self.assertIsNone(result)
        self.assertEqual(output, ["first second", "true"])
        self.assertFalse(file_path.exists())

    def test_await_is_restricted_to_async_functions(self):
        with self.assertRaisesRegex(ParseError, "only valid inside an async function"):
            self.run_x("""
                function main() {
                    await sleep(1);
                }
                """)

        with self.assertRaisesRegex(
            RuntimeErrorX, "await requires an asynchronous operation"
        ):
            self.run_x("""
                async function main() {
                    await 42;
                }
                """)

    def test_sleep_requires_a_non_negative_millisecond_duration(self):
        start_time = monotonic()
        self.run_x("""
            async function main() {
                await sleep(30);
            }
            """)
        elapsed_seconds = monotonic() - start_time
        self.assertGreaterEqual(elapsed_seconds, 0.025)

        with self.assertRaisesRegex(RuntimeErrorX, "duration cannot be negative"):
            self.run_x("""
                async function main() {
                    await sleep(-1);
                }
                """)

    def test_rest_parameters_and_array_call_object_spread(self):
        result, output = self.run_x("""
            integer function sum(integer ...values) {
                let integer total = 0;
                for (integer value in values) {
                    total += value;
                }
                return total;
            }
            function main() {
                let integer[] first = [1, 2];
                let integer[] combined = [0, ...first, 3];
                print(sum(...combined));
                print(sum());

                let object base = {name: "Ada", role: "Engineer"};
                let object profile = {...base, role: "Architect"};
                print(profile.name + " " + profile.role);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["6", "0", "Ada Architect"])

    def test_async_await_and_concurrent_all(self):
        result, output = self.run_x("""
            import System.concurrent.Async
            let string[] completed = [];

            async function fetch(string name, integer milliseconds) {
                await Async.delay(milliseconds);
                completed.add(name);
                return name;
            }

            async function main() {
                let string[] results = await Async.all([
                    fetch("slow", 60),
                    fetch("fast", 5)
                ]);
                print(results[0] + ", " + results[1]);
                print(completed[0]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["slow, fast", "fast"])

    def test_thread_start_and_join(self):
        result, output = self.run_x("""
            import System.concurrent.Thread

            integer function add(integer left, integer right) {
                return left + right;
            }
            integer function getAnswer() {
                return 42;
            }

            function main() {
                let ThreadHandle worker = Thread.start(add, [20, 22]);
                print(worker.join());
                print(worker.isAlive());

                let ThreadHandle noArgumentWorker = Thread.start(getAnswer);
                print(noArgumentWorker.join());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["42", "false", "42"])

    def test_new_runs_constructor_and_super_calls_parent_constructor(self):
        result, output = self.run_x("""
            class Parent {
                private string name;
                public Parent(string name) {
                    this.name = name;
                }
                public string getName() {
                    return this.name;
                }
            }
            class Child extends Parent {
                public Child(string name) {
                    super(name);
                }
                public string describe() {
                    return super.getName() + " from child";
                }
            }
            function main() {
                let Child child = new Child("X");
                print(child.describe());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["X from child"])

    def test_empty_array_remains_an_array_value(self):
        result, output = self.run_x("""
            function main() {
                let string[] values = [];
                print(values.length);
                values.add("ready");
                print(values[0]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["0", "ready"])

    def test_for_loop_accepts_let_and_const_bindings(self):
        result, output = self.run_x("""
            function main() {
                for (let number in range(1, 3, 1)) {
                    print(number);
                }
                for (const label in ["x", "y"]) {
                    print(label);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["1", "2", "x", "y"])

    def test_all_loop_forms(self):
        result, output = self.run_x("""
            function main() {
                let integer total = 0;
                for (let index = 0; index < 3; index++) {
                    total += index;
                }
                do {
                    total++;
                } while (total < 5);

                let object valuesByName = {first: 10, second: 20};
                for (let key in valuesByName) {
                    print(key);
                }

                for (let value of [total, 6]) {
                    print(value);
                }
                print(rangeTotal());
            }
            integer function rangeTotal() {
                let integer sum = 0;
                for (integer value in range(1, 4, 1)) {
                    sum += value;
                }
                return sum;
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["first", "second", "5", "6", "6"])

    def test_runtime_exceptions_support_multiple_catches_and_finally(self):
        result, output = self.run_x("""
            function main() {
                let string[] events = [];
                try {
                    let integer bad = "not a number" - 1;
                }
                catch (IOException error) {
                    events.add("io");
                }
                catch (RuntimeException | IllegalArgumentException error) {
                    events.add(error.name);
                    events.add(error.message);
                }
                finally {
                    events.add("finally");
                }
                for (string event in events) {
                    print(event);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            ["TypeException", "Invalid operands for '-'", "finally"],
        )

    def test_finally_runs_when_try_returns_and_when_catch_throws(self):
        result, output = self.run_x("""
            integer function returnsThroughFinally() {
                try {
                    return 5;
                }
                finally {
                    print("finally after return");
                }
            }
            function main() {
                print(returnsThroughFinally());
                try {
                    try {
                        throw new Exception("first");
                    }
                    catch (Exception error) {
                        throw new Exception("second");
                    }
                    finally {
                        print("inner finally");
                    }
                }
                catch (Exception error) {
                    print(error.message);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            ["finally after return", "5", "inner finally", "second"],
        )

    def test_match_expression_patterns_bind_and_guard(self):
        result, output = self.run_x("""
            enum Status {
                READY,
                DONE
            }
            function describe(object value) {
                return match value {
                    null => "empty",
                    [first, second, ...remaining] if first == 1 =>
                        "array " + second + " tail " + remaining.length,
                    {name: person, active: true} => "person " + person,
                    _ => "other"
                };
            }
            function main() {
                print(describe(null));
                print(describe([1, 2, 3, 4]));
                print(describe({name: "Ada", active: true}));
                let Status status = Status.DONE;
                let string label = match status {
                    Status.READY => "ready",
                    Status.DONE => "done"
                };
                print(label);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            ["empty", "array 2 tail 2", "person Ada", "done"],
        )

    def test_enum_matching_and_cross_enum_equality(self):
        result, output = self.run_x("""
            enum Foo {
                SAME
            }
            enum Bar {
                SAME
            }
            function main() {
                print(Foo.SAME == Foo.SAME);
                print(Foo.SAME == Bar.SAME);
                print(Foo.SAME === Bar.SAME);
                print(1 == "1");
                print(1 === "1");
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["true", "false", "false", "true", "false"])

    def test_enums_can_be_declared_in_function_and_nested_block_scopes(self):
        result, output = self.run_x("""
            function main() {
                enum Status {
                    READY,
                    DONE
                }
                let Status current = Status.DONE;
                print(match current {
                    Status.READY => "ready",
                    Status.DONE => "done"
                });

                {
                    enum Status {
                        DONE
                    }
                    print(current == Status.DONE);
                    print(match Status.DONE {
                        Status.DONE => "inner done"
                    });
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["done", "false", "inner done"])

    def test_function_and_class_decorators(self):
        result, output = self.run_x("""
            function identity(var target) { return target; }
            @trace
            function greet() { return "hello"; }
            @identity
            function unchanged() { return "unchanged"; }
            @trace
            class Box {
                public Box() {}
                @trace
                public string value() { return "box"; }
            }
            function main() {
                print(greet());
                print(unchanged());
                print(new Box().value());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(
            output,
            [
                "Calling greet",
                "hello",
                "unchanged",
                "Constructing Box",
                "Calling value",
                "box",
            ],
        )

    def test_namespace_and_nested_class_construction(self):
        result, output = self.run_x("""
            namespace App.Models {
                class User {
                    public string name;
                    public User(string name) { this.name = name; }
                }
            }
            class Container {
                class Item {
                    public string label;
                    public Item(string label) { this.label = label; }
                }
            }
            function main() {
                let App.Models.User user = new App.Models.User("Ada");
                let Container.Item item = new Container.Item("book");
                print(user.name);
                print(item.label);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Ada", "book"])

    def test_array_and_object_destructuring_declarations_and_assignment(self):
        result, output = self.run_x("""
            function main() {
                const [first, second = 20, ...remaining] = [10];
                let source = { name: "Ada", age: 36, active: true };
                let { name, age: years, ...other } = source;
                let left = 0;
                let right = 0;
                [left, right] = [3, 4];
                print(first);
                print(second);
                print(remaining.length);
                print(name + years);
                print(other.active);
                ({name: name} = {name: "Grace"});
                print(name);
                print(left + right);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["10", "20", "0", "Ada36", "true", "Grace", "7"])

    def test_for_of_supports_destructuring_bindings(self):
        result, output = self.run_x("""
            function main() {
                for (const [name, score] of [["Ada", 10], ["Lin", 12]]) {
                    print(name + score);
                }
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["Ada10", "Lin12"])

    def test_automatic_semicolon_insertion_int_alias_and_object_helpers(self):
        result, output = self.run_x("""
            int function main()
            {
                let value = 4
                const record = { value, "display-name": "sample" }
                print(record.value)
                print(record["display-name"])
                print(Object.keys(record).length)
                print(Object.hasOwn(record, "value"))
                print(Object.values(record).length)
                let copied = Object.assign({}, record)
                print(Object.entries(copied).length)
                return value
            }
            """)
        self.assertEqual(result, 4)
        self.assertEqual(output, ["4", "sample", "2", "true", "2", "2"])

    def test_constants_cannot_be_reassigned(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Cannot reassign constant"):
            self.run_x("""
                function main() {
                    const integer limit = 2;
                    limit = 3;
                }
                """)

    def test_typed_arrays_reject_wrong_elements_and_invalid_mutations(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Expected 'integer'.*index 2.*got 'string'"
        ):
            self.run_x("""
                function main() {
                    let integer[] values = [1, 2, "name"];
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'integer' for array item"):
            self.run_x("""
                function main() {
                    let integer[] values = [1, 2];
                    values.add("name");
                }
                """)

        with self.assertRaisesRegex(RuntimeErrorX, "Expected 'integer' for array item"):
            self.run_x("""
                function main() {
                    let integer[] values = [1, 2];
                    values[0] = "name";
                }
                """)

    def test_typed_array_parameters_validate_each_element(self):
        result, output = self.run_x("""
            function appendValue(integer[] values) { values.add(2); }
            function main() {
                let integer[] values = [1];
                appendValue(values);
                print(values.length);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["2"])

        with self.assertRaisesRegex(RuntimeErrorX, "No overload of 'accept' matches"):
            self.run_x("""
                function accept(integer[] values) {}
                function main() {
                    accept([1, "name"]);
                }
                """)

    def test_typed_array_metadata_does_not_leak_into_shadowed_variables(self):
        result, output = self.run_x("""
            function main() {
                let integer[] values = [1];
                {
                    let values = ["local"];
                    values = ["updated"];
                    print(values[0]);
                }
                print(values[0]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["updated", "1"])

    def test_system_environment_values_are_accessible_as_members(self):
        result, output = self.run_x(
            """
            function main() {
                print(System.Environment.X_PROJECT);
            }
            """,
            environment={"X_PROJECT": "x-language"},
        )
        self.assertIsNone(result)
        self.assertEqual(output, ["x-language"])

        with self.assertRaisesRegex(RuntimeErrorX, "Name 'get' is not defined"):
            self.run_x(
                """
                function main() {
                    print(System.Environment.get("X_PROJECT"));
                }
                """,
                environment={"X_PROJECT": "x-language"},
            )

    def test_access_modifiers_are_enforced_with_public_default(self):
        result, output = self.run_x("""
            class Base {
                private string secret;
                protected string inheritedValue;
                string publicByDefault;
                public Base() {
                    this.secret = "hidden";
                    this.inheritedValue = "inherited";
                    this.publicByDefault = "visible";
                }
                private string privateMethod() { return this.secret; }
                string defaultMethod() { return this.publicByDefault; }
                public string readSecret() { return this.privateMethod(); }
            }
            class Derived extends Base {
                public Derived() { super(); }
                public string inherited() { return this.inheritedValue; }
            }
            function main() {
                let Base base = new Base();
                let Derived derived = new Derived();
                print(base.publicByDefault);
                print(base.defaultMethod());
                print(base.readSecret());
                print(derived.inherited());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["visible", "visible", "hidden", "inherited"])

    def test_private_and_protected_members_cannot_be_accessed_externally(self):
        for access_expression, expected_access in (
            ("value.secret", "private property"),
            ('value.secret = "public"', "private property"),
            ("value.hidden()", "private method"),
            ("value.protectedValue", "protected property"),
        ):
            with self.subTest(access_expression=access_expression):
                with self.assertRaisesRegex(RuntimeErrorX, expected_access):
                    self.run_x(f"""
                        class Vault {{
                            private string secret;
                            protected string protectedValue;
                            public Vault() {{
                                this.secret = "secret";
                                this.protectedValue = "protected";
                            }}
                            private string hidden() {{ return this.secret; }}
                        }}
                        function main() {{
                            let Vault value = new Vault();
                            print({access_expression});
                        }}
                        """)

    def test_final_class_cannot_be_extended(self):
        with self.assertRaisesRegex(
            RuntimeErrorX, "Cannot extend final class 'Closed'"
        ):
            self.run_x("""
                final class Closed {}
                class Open extends Closed {}
                function main() {}
                """)

    def test_strings_support_unicode_code_point_indexing(self):
        result, output = self.run_x("""
            function main() {
                let string sample = "Aé🙂";
                print(sample.length);
                print(sample[0]);
                print(sample[2]);
                print(sample[-1]);
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["3", "A", "🙂", "🙂"])

    def test_static_private_members_are_accessible_only_inside_the_class(self):
        result, output = self.run_x("""
            class Credentials {
                private static string secret = "hidden";
                private static string readSecret() {
                    return Credentials.secret;
                }
                public static string reveal() {
                    return Credentials.readSecret();
                }
            }
            function main() {
                print(Credentials.reveal());
            }
            """)
        self.assertIsNone(result)
        self.assertEqual(output, ["hidden"])
        with self.assertRaisesRegex(RuntimeErrorX, "private property"):
            self.run_x("""
                class Credentials {
                    private static string secret = "hidden";
                }
                function main() { print(Credentials.secret); }
                """)

    def test_string_index_errors_include_runtime_failure(self):
        with self.assertRaisesRegex(RuntimeErrorX, "Cannot access index 4"):
            self.run_x("""
                function main() {
                    let string sample = "abc";
                    print(sample[4]);
                }
                """)


if __name__ == "__main__":
    unittest.main()
