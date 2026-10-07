import System.io.Console

any function testNestedSwitch(any x, any y) {
    switch (x) {
        case 1: {
            Console.print("x is 1")
            switch (y) {
                case 10: {
                    Console.print("  y is 10")
                }
                case 20: {
                    Console.print("  y is 20")
                }
                default: {
                    Console.print("  y is other: " + y)
                }
            }
        }
        case 2: {
            Console.print("x is 2")
        }
        default: {
            Console.print("x is other: " + x)
        }
    }
}

testNestedSwitch(1, 10)
testNestedSwitch(1, 20)
testNestedSwitch(1, 30)
testNestedSwitch(2, 10)
testNestedSwitch(3, 10)