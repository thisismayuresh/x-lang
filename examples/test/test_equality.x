import System.io.Console

Console.print("=== Equality Tests ===")

Console.print("\n--- Primitive Equality ===")
Console.print("1 == 1:", 1 == 1)
Console.print("1 != 1:", 1 != 1)
Console.print("1 === 1:", 1 === 1)
Console.print("1 !== 1:", 1 !== 1)

Console.print("1 == 2:", 1 == 2)
Console.print("1 != 2:", 1 != 2)
Console.print("1 === 2:", 1 === 2)
Console.print("1 !== 2:", 1 !== 2)

Console.print("1.5 == 1.5:", 1.5 == 1.5)
Console.print("1.5 === 1.5:", 1.5 === 1.5)

Console.print("true == true:", true == true)
Console.print("false == true:", false == true)
Console.print("true === false:", true === false)

Console.print("'hello' == 'hello':", "hello" == "hello")
Console.print("'hello' === 'hello':", "hello" === "hello")
Console.print("'hello' == 'world':", "hello" == "world")

Console.print("\n--- Array Equality ===")
let arr1 = [1, 2, 3]
let arr2 = [1, 2, 3]
let arr3 = [1, 2, 4]
let arr4 = [1, 2, 3, 4]

Console.print("[1,2,3] == [1,2,3]:", arr1 == arr2)
Console.print("[1,2,3] === [1,2,3]:", arr1 === arr2)
Console.print("[1,2,3] == [1,2,4]:", arr1 == arr3)
Console.print("[1,2,3] === [1,2,4]:", arr1 === arr3)
Console.print("[1,2,3] == [1,2,3,4]:", arr1 == arr4)
Console.print("[1,2,3] === [1,2,3,4]:", arr1 === arr4)

Console.print("[] == []:", [] == [])
Console.print("[] === []:", [] === [])
Console.print("[] != [1]:", [] != [1])
Console.print("[] !== [1]:", [] !== [1])

Console.print("\n--- String Equality ===")
Console.print("'' == '':", "" == "")
Console.print("'' === '':", "" === "")
Console.print("'a' == 'a':", "a" == "a")
Console.print("'a' === 'a':", "a" === "a")
Console.print("'a' == 'b':", "a" == "b")

Console.print("\n--- Null/Undefined Equality ===")
Console.print("null == null:", null == null)
Console.print("null === null:", null === null)
Console.print("undefined == undefined:", undefined == undefined)
Console.print("undefined === undefined:", undefined === undefined)
Console.print("null == undefined:", null == undefined)
Console.print("null === undefined:", null === undefined)

Console.print("\n--- Object Equality ===")
let obj1 = { "a": 1, "b": 2 }
let obj2 = { "a": 1, "b": 2 }
let obj3 = { "a": 1 }
let obj4 = { "b": 2, "a": 1 }

Console.print("{a:1,b:2} == {a:1,b:2}:", obj1 == obj2)
Console.print("{a:1,b:2} === {a:1,b:2}:", obj1 === obj2)
Console.print("{a:1} == {a:1,b:2}:", obj1 == obj3)

Console.print("\n--- Cross-type Equality (strict mode) ===")
Console.print("1 == '1':", 1 == "1")
Console.print("1 === '1':", 1 === "1")
Console.print("1 == true:", 1 == true)
Console.print("1 === true:", 1 === true)
Console.print("0 == false:", 0 == false)
Console.print("0 === false:", 0 === false)
Console.print("'' == false:", "" == false)
Console.print("'' === false:", "" === false)

Console.print("\n--- Nested Array Equality ===")
let nested1 = [[1,2],[3,4]]
let nested2 = [[1,2],[3,4]]
let nested3 = [[1,2],[3,5]]

Console.print("[[1,2],[3,4]] == [[1,2],[3,4]]:", nested1 == nested2)
Console.print("[[1,2],[3,4]] === [[1,2],[3,4]]:", nested1 === nested2)
Console.print("[[1,2],[3,4]] == [[1,2],[3,5]]:", nested1 == nested3)

Console.print("\n--- TypeOf Tests ===")
Console.print("typeOf(1):", typeOf(1))
Console.print("typeOf(1.5):", typeOf(1.5))
Console.print("typeOf(true):", typeOf(true))
Console.print("typeOf('hello'):", typeOf("hello"))
Console.print("typeOf([]):", typeOf([]))
Console.print("typeOf([1,2]):", typeOf([1,2]))
Console.print("typeOf({}):", typeOf({}))
Console.print("typeOf(null):", typeOf(null))
Console.print("typeOf(undefined):", typeOf(undefined))

Console.print("\n--- All tests completed ===")