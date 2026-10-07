import System.concurrent.Thread

string function formatJob(string jobName, integer jobNumber) {
    return "Finished " + jobName + " #" + jobNumber;
}

any function main() {
    let ThreadHandle firstWorker = Thread.start(formatJob, ["compile", 1]);
    let ThreadHandle secondWorker = Thread.start(formatJob, ["test", 2]);

    print(firstWorker.join());
    print(secondWorker.join());
    print("Workers still running: " + firstWorker.isAlive());
}
