package examples.queue

import examples.queue.Queue

export enum JobStatus {
    WAITING,
    RUNNING,
    COMPLETE
}

export class QueueDemo {
    public void run(string[] args) {
        this.showRangeLoop();
        this.showIterableLoop();
        this.showWhileLoop();
        this.showQueue();
        this.runQueueTests();
        this.showEnum();
        this.showArguments(args);
    }

    private void showRangeLoop() {
        print("Range loop (1 through 5):");
        let integer total = 0;

        for (integer number in range(1, 6, 1)) {
            print(number);
            total += number;
        }

        print("Sum: " + total);
    }

    private void showIterableLoop() {
        print("Iterable loop:");
        let string[] names = ["Ada", "Grace", "Linus"];

        for (string name in names) {
            print("Hello, " + name);
        }
    }

    private void showWhileLoop() {
        print("While loop countdown:");
        let integer countdown = 3;

        while (countdown > 0) {
            print(countdown);
            countdown--;
        }
    }

    private void showQueue() {
        print("Queue operations:");
        let Queue<string> queue = Queue<string>();
        queue.enqueue("compile");
        queue.enqueue("test");
        queue.enqueue("package");

        print("Front item: " + queue.peek());
        print("Queue size: " + queue.size());

        while (!queue.isEmpty()) {
            print("Dequeued: " + queue.dequeue());
        }
    }

    private void runQueueTests() {
        this.testFifoOrder();
        this.testPeekDoesNotRemoveItem();
        this.testSizeAndEmptyState();
        this.testDequeueRejectsEmptyQueue();
        print("All queue tests passed.");
    }

    private void testFifoOrder() {
        let Queue<integer> queue = Queue<integer>();
        queue.enqueue(10);
        queue.enqueue(20);
        queue.enqueue(30);

        this.assertEqual(queue.dequeue(), 10, "FIFO first item");
        this.assertEqual(queue.dequeue(), 20, "FIFO second item");
        this.assertEqual(queue.dequeue(), 30, "FIFO third item");
    }

    private void testPeekDoesNotRemoveItem() {
        let Queue<string> queue = Queue<string>();
        queue.enqueue("front");

        this.assertEqual(queue.peek(), "front", "peek returns front item");
        this.assertEqual(queue.size(), 1, "peek does not remove item");
    }

    private void testSizeAndEmptyState() {
        let Queue<integer> queue = Queue<integer>();
        this.assertTrue(queue.isEmpty(), "new queue is empty");
        this.assertEqual(queue.size(), 0, "new queue size is zero");

        queue.enqueue(1);
        queue.enqueue(2);
        this.assertEqual(queue.size(), 2, "enqueue increases size");
        queue.dequeue();
        this.assertEqual(queue.size(), 1, "dequeue decreases size");
        queue.dequeue();
        this.assertTrue(queue.isEmpty(), "queue is empty after removing all items");
    }

    private void testDequeueRejectsEmptyQueue() {
        let Queue<string> queue = Queue<string>();
        let boolean exceptionCaught = false;

        try {
            queue.dequeue();
        }
        catch (Exception error) {
            exceptionCaught = true;
        }

        this.assertTrue(exceptionCaught, "empty dequeue throws");
    }

    private void showEnum() {
        print("Enum value: " + JobStatus.WAITING);
    }

    private void showArguments(string[] args) {
        if (args.length == 0) {
            print("No command-line name supplied.");
            return;
        }

        print("Command-line name: " + args[0]);
    }

    private void assertTrue(boolean condition, string description) {
        if (!condition) {
            throw new Exception("Queue test failed: " + description);
        }
    }

    private void assertEqual(string actual, string expected, string description) {
        if (actual != expected) {
            throw new Exception("Queue test failed: " + description);
        }
    }

    private void assertEqual(integer actual, integer expected, string description) {
        if (actual != expected) {
            throw new Exception("Queue test failed: " + description);
        }
    }
}
