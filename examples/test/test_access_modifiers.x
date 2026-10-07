class Test {
    private int x = 1
    protected int y = 2
    public int z = 3
}

let t = new Test()
print(t.x)  // Should error - private
print(t.y)  // Should error - protected
print(t.z)  // Should work - public