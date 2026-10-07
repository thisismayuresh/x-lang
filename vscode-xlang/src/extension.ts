import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { LanguageClient, LanguageClientOptions, ServerOptions, TransportKind } from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: vscode.ExtensionContext) {
    console.log('X Language extension is now active');

    // The server is implemented in Python
    const serverModule = context.asAbsolutePath(
        path.join('server', 'server.py')
    );

    // Check if server exists
    if (!fs.existsSync(serverModule)) {
        vscode.window.showErrorMessage(
            'X Language server not found. Please run "npm install" in the server directory.'
        );
        return;
    }

    // The debug options for the server
    const debugOptions = { execArgv: ['--nolazy', '--inspect=6009'] };

    // If the extension is launched in debug mode then the debug server options are used
    // Otherwise the run options are used
    const serverOptions: ServerOptions = {
        run: { command: 'python', args: [serverModule], transport: TransportKind.stdio, options: {} } as any,
        debug: { command: 'python', args: [serverModule], transport: TransportKind.stdio, options: debugOptions } as any
    };

    // Options to control the language client
    const clientOptions: LanguageClientOptions = {
        // Register the server for X documents
        documentSelector: [{ scheme: 'file', language: 'x' }],
        synchronize: {
            // Notify the server about file changes to .x files contained in the workspace
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.x'),
            // Synchronize the setting section 'xlang' to the server
            configurationSection: 'xlang'
        },
        initializationOptions: {
            // Send initial config to server
        },
        middleware: {
            // Optional: Add middleware for custom handling
        }
    };

    // Create the language client and start the client
    client = new LanguageClient(
        'xlang',
        'X Language Server',
        serverOptions,
        clientOptions
    );

    // Start the client. This will also launch the server
    client.start();

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('xlang.restartServer', () => {
            client.stop().then(() => {
                client.start();
                vscode.window.showInformationMessage('X Language Server restarted');
            });
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('xlang.checkFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (editor && editor.document.languageId === 'x') {
                // Force a re-check by sending a didSave notification
                await client.sendNotification('textDocument/didSave', {
                    textDocument: { uri: editor.document.uri.toString() }
                });
                vscode.window.showInformationMessage('Type check triggered');
            }
        })
    );

    // Watch for configuration changes
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('xlang')) {
                client.sendNotification('workspace/didChangeConfiguration', {
                    settings: vscode.workspace.getConfiguration('xlang')
                });
            }
        })
    );
}

export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}