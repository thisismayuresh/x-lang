// Inline imports — bring just what you need from Collections
import System.utils.Collections.List
import System.utils.Collections.Stack

// Student type shape defined as an interface
interface Student {
    string name;
    integer age;
    string major;
    float gpa;
}

function printStudent(Student student) {
    print(`  Name: {student.name} | Age: {student.age} | Major: {student.major} | GPA: {student.gpa}`)
}

function main() {

    let nums = [1,2,3,4,5]
    print("nums of",nums[0])

    for (integer n of nums) {
        print(n)
    }

    // ── List<Student> ───────────────────────────────────────────────────
    print("=== Student Registry (List<Student>) ===\n")

    let List<Student> students = new List<Student>()

    // Add 5 students using OOP-style dot calls
    students.add({ name: "Alice Chen",   age: 20, major: "Computer Science", gpa: 3.9 })
    students.add({ name: "Bob Martins",  age: 22, major: "Mathematics",      gpa: 3.5 })
    students.add({ name: "Carol Singh",  age: 21, major: "Data Science",     gpa: 3.8 })
    students.add({ name: "Dave Okonkwo", age: 23, major: "Software Eng.",    gpa: 3.7 })
    students.add({ name: "Eve Larsson",  age: 20, major: "Cybersecurity",    gpa: 3.6 })

    print(`Total students enrolled: {students.size()}\n`)

    // ── for (integer i in range) — index-based traversal ──────────────
    print("All Students (for integer i in range):")
    let Student[] arr = students.toArray()
    for (integer i in range(0, students.size())) {
        print(`  [{i}] {arr[i].name} | Age: {arr[i].age} | Major: {arr[i].major} | GPA: {arr[i].gpa}`)
    }

    // ── for...of — element-based traversal ────────────────────────────
    print("\nAll Students (for Student s of array):")
    for (Student s of arr) {
        printStudent(s)
    }

    // Random access via dot-style methods
    print(`\nFirst student : {students.getFirst().name}`)
    print(`Last student  : {students.getLast().name}`)
    print(`Student at [2]: {students.get(2).name}`)

    // ── Stack<string> ────────────────────────────────────────────────────
    print("\n=== Course History (Stack<string>) ===\n")

    let Stack<string> courseHistory = new Stack<string>()

    courseHistory.push("Intro to Programming")
    courseHistory.push("Data Structures")
    courseHistory.push("Algorithms")
    courseHistory.push("Operating Systems")
    courseHistory.push("Machine Learning")

    print(`Courses taken : {courseHistory.size()}`)
    print(`Latest course : {courseHistory.peek()}`)

    print("\nCourse history (most recent first):")
    while (!courseHistory.isEmpty()) {
        print(`  - {courseHistory.pop()}`)
    }

}
