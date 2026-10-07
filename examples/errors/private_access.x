class Vault {
    protected string secret;

    public Vault() {
        this.secret = "classified";
    }
}

any function main() {
    let Vault vault = new Vault();
    print(vault.secret);
}
