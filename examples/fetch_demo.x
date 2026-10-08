// System.io.Network.http — the awaitable fetch() with HttpException handling.
// Also shows: import paths that mirror the exception hierarchy, an inline
// qualified catch clause, and System.utils.JSON.toJSON (JSON.stringify-like).
// Runs offline too: a failed request falls into catch/finally instead of crashing.
import System.io.Network.http.fetch
import System.Throwable.Exception.IOException.HttpException
import System.utils.JSON.toJSON

async function main() {
    // Headers pass straight through to the request — including User-Agent,
    // which beats the userAgent option and the library default.
    let headers = {
        "User-Agent": "X-Lang-Demo/1.0 (fetch_demo.x)",
        "Accept": "application/json"
    };
    try {
        let response = await fetch("https://dummyjson.com/posts", {
            headers: headers,
            timeout: 15
        });

        print("status: " + response.status + " " + response.statusText);
        print("ok: " + response.ok);
        print("content-type: " + response.header("content-type"));
        print("body bytes: " + response.bodyBytes.length);

        // body is raw text — response.json() parses it into objects/arrays.
        let data = response.json();
        print("posts: " + data.posts.length);
        print("first post: " + data.posts[0].title);
        print("To jsonnnnn", toJSON(data.posts[0], 2));

        // toJSON(value) is compact, toJSON(value, indent) pretty-prints —
        // same shapes as JavaScript's JSON.stringify.
        let summary = {
            url: response.url,
            status: response.status,
            ok: response.ok,
            fetched: true
        };
        print(toJSON(summary));
    } catch (System.Throwable.Exception.IOException.HttpException error) {
        // Fully-qualified catch type, written inline: no cast, no wrapper.
        print("request failed: " + error.message);
    } finally {
        print("done");
    }
}
