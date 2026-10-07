import System.io.Console

function testSwitch(value) {
    switch (value) {
        case 1: {
            Console.print("One")
        }
        case 2: {
            Console.print("Two")
        }
        case 3: {
            Console.print("Three")
        }
        default: {
            Console.print("Other: " + value)
        }
    }
}

testSwitch(1)
testSwitch(2)
testSwitch(3)
testSwitch(5)