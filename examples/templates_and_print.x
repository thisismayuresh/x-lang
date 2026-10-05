function main() {
    let string name = "Maya";
    let integer count = 3;

    print("My Name " + "is", "Maya");
    print("My Name " + "is", name);
    print(`Hello {name}. 2 + 1 = {2 + 1}.`);
    print(`This template spans
multiple lines, and still interpolates {count}.`);
    print(`Use {{ and }} to show braces without interpolation.`);
    print("Arrays:", [1, 2, 3], "objects:", {active: true});
}
