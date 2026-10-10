export interface Gateway {
    integer process(integer amount);
    string name();
}

export class StripeGateway implements Gateway {
    private string region;

    public StripeGateway(string region) {
        this.region = region;
    }

    public integer process(integer amount) {
        return amount + 10;
    }

    public string name() {
        return "stripe-" + this.region;
    }
}

export class PaypalGateway implements Gateway {
    public integer process(integer amount) {
        return amount + 20;
    }

    public string name() {
        return "paypal";
    }
}
