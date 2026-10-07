"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const node_1 = require("vscode-languageclient/node");
let client;
function activate(context) {
    console.log('X Language extension is now active');
    // The server is implemented in Python
    const serverModule = context.asAbsolutePath(path.join('server', 'server.py'));
    // Check if server exists
    if (!fs.existsSync(serverModule)) {
        vscode.window.showErrorMessage('X Language server not found. Please run "npm install" in the server directory.');
        return;
    }
    // The debug options for the server
    const debugOptions = { execArgv: ['--nolazy', '--inspect=6009'] };
    // If the extension is launched in debug mode then the debug server options are used
    // Otherwise the run options are used
    const serverOptions = {
        run: { command: 'python', args: [serverModule], transport: node_1.TransportKind.stdio, options: {} },
        debug: { command: 'python', args: [serverModule], transport: node_1.TransportKind.stdio, options: debugOptions }
    };
    // Options to control the language client
    const clientOptions = {
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
    client = new node_1.LanguageClient('xlang', 'X Language Server', serverOptions, clientOptions);
    // Start the client. This will also launch the server
    client.start();
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand('xlang.restartServer', () => {
        client.stop().then(() => {
            client.start();
            vscode.window.showInformationMessage('X Language Server restarted');
        });
    }));
    context.subscriptions.push(vscode.commands.registerCommand('xlang.checkFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document.languageId === 'x') {
            // Force a re-check by sending a didSave notification
            await client.sendNotification('textDocument/didSave', {
                textDocument: { uri: editor.document.uri.toString() }
            });
            vscode.window.showInformationMessage('Type check triggered');
        }
    }));
    // Watch for configuration changes
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
        if (e.affectsConfiguration('xlang')) {
            client.sendNotification('workspace/didChangeConfiguration', {
                settings: vscode.workspace.getConfiguration('xlang')
            });
        }
    }));
}
function deactivate() {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
//# sourceMappingURL=extension.js.map