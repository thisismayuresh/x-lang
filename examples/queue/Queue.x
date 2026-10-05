package examples.queue

export class Queue<T> {
    private T[] items = [];
    private integer head = 0;
    private integer tail = 0;

    public void enqueue(T item) {
        this.items.add(item);
        this.tail++;
    }

    public T dequeue() {
        if (this.isEmpty()) {
            throw new Exception("Cannot dequeue from an empty queue.");
        }

        let T item = this.items[this.head];
        this.head++;
        return item;
    }

    public T peek() {
        if (this.isEmpty()) {
            throw new Exception("Cannot peek at an empty queue.");
        }

        return this.items[this.head];
    }

    public boolean isEmpty() {
        return this.head == this.tail;
    }

    public integer size() {
        return this.tail - this.head;
    }
}
