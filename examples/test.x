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

string function getMessage(string message) {
    return "Hello " + message;
}

Data[] function getData(int id) {
    return [{name: "record " + id}];
}

string function onComplete() {
    return "callback finished";
}

string function myX(Function myfunc) {
    return "Hello " + myfunc();
}

any function main() {
    let IMyInterface service = {
        getMessage: getMessage,
        getData: getData,
        primary: {name: "primary"},
        records: [{name: "cached"}],
        onComplete: onComplete
    };
    let function callback = service.onComplete;

    print(service.getMessage("Maya"));
    print(service.getData(1)[0].name);
    print(service.primary.name, service.records[0].name);
    print(myX(callback));
}
