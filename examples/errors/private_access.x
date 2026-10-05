class Vault {
    protected string secret;

    public Vault() {
        this.secret = "classified";
    }
}

function main() {
    let Vault vault = new Vault();
    print(vault.secret);
}
