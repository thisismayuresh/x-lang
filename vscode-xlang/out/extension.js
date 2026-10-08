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
const child_process_1 = require("child_process");
const node_1 = require("vscode-languageclient/node");
let client;
let outputChannel;
function log(message) {
    outputChannel?.appendLine(message);
    console.log(`[xlang] ${message}`);
}
function canImport(python, module) {
    try {
        const result = (0, child_process_1.spawnSync)(python, ['-c', `import ${module}`], {
            timeout: 5000,
            windowsHide: true
        });
        return result.status === 0;
    }
    catch {
        return false;
    }
}
function isExecutable(candidate) {
    if (candidate.includes(path.sep) || path.isAbsolute(candidate)) {
        return fs.existsSync(candidate);
    }
    return true;
}
function resolvePython(workspaceFolders) {
    const configured = (vscode.workspace.getConfiguration('xlang').get('pythonPath') ?? '').trim();
    if (configured) {
        return configured;
    }
    const candidates = [];
    for (const folder of workspaceFolders ?? []) {
        const root = folder.uri.fsPath;
        candidates.push(path.join(root, '.venv', 'bin', 'python'));
        candidates.push(path.join(root, 'venv', 'bin', 'python'));
        candidates.push(path.join(root, '.venv', 'Scripts', 'python.exe'));
        candidates.push(path.join(root, 'venv', 'Scripts', 'python.exe'));
    }
    candidates.push('python3', 'python');
    for (const candidate of candidates) {
        if (!isExecutable(candidate)) {
            continue;
        }
        if (canImport(candidate, 'pygls')) {
            return candidate;
        }
    }
    const firstExisting = candidates.find(c => c.includes(path.sep) && fs.existsSync(c));
    return firstExisting ?? 'python3';
}
function resolveServerModule(context) {
    const configured = (vscode.workspace.getConfiguration('xlang').get('serverPath') ?? '').trim();
    if (configured) {
        return configured;
    }
    return context.asAbsolutePath(path.join('server', 'server.py'));
}
function readSettings() {
    const config = vscode.workspace.getConfiguration('xlang');
    return {
        enableTypeChecking: config.get('enableTypeChecking', true),
        strictTyping: config.get('strictTyping', false)
    };
}
function buildServerEnv(workspaceFolders) {
    const env = { ...process.env };
    const roots = (workspaceFolders ?? []).map(folder => folder.uri.fsPath);
    if (roots.length > 0) {
        env.PYTHONPATH = env.PYTHONPATH
            ? [...roots, env.PYTHONPATH].join(path.delimiter)
            : roots.join(path.delimiter);
    }
    return env;
}
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('X Language', { log: true });
    log('X Language extension activated');
    const serverModule = resolveServerModule(context);
    if (!fs.existsSync(serverModule)) {
        vscode.window.showErrorMessage(`X Language server not found at ${serverModule}`);
        return;
    }
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const python = resolvePython(workspaceFolders);
    log(`Using interpreter: ${python}`);
    log(`Using server: ${serverModule}`);
    if (!canImport(python, 'pygls')) {
        const message = `The Python interpreter used by X Language (${python}) is missing pygls. ` +
            'Install it (pip install pygls lsprotocol) or set "xlang.pythonPath".';
        log(message);
        vscode.window.showWarningMessage(message);
    }
    const env = buildServerEnv(workspaceFolders);
    const cwd = workspaceFolders?.[0]?.uri.fsPath;
    const serverOptions = {
        run: {
            command: python,
            args: [serverModule],
            transport: node_1.TransportKind.stdio,
            options: { env, cwd }
        },
        debug: {
            command: python,
            args: [serverModule],
            transport: node_1.TransportKind.stdio,
            options: { env, cwd }
        }
    };
    const clientOptions = {
        documentSelector: [{ scheme: 'file', language: 'x' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.{x,toml}')
        },
        initializationOptions: readSettings(),
        outputChannel
    };
    client = new node_1.LanguageClient('xlang', 'X Language Server', serverOptions, clientOptions);
    client.start().then(() => log('X Language Server started'), (error) => {
        const message = error instanceof Error ? error.message : String(error);
        log(`X Language Server failed to start: ${message}`);
        vscode.window.showErrorMessage(`X Language Server failed to start. See the "X Language" output channel for details.`);
    });
    context.subscriptions.push(vscode.commands.registerCommand('xlang.restartServer', async () => {
        if (!client) {
            return;
        }
        try {
            await client.stop();
            await client.start();
            vscode.window.showInformationMessage('X Language Server restarted');
        }
        catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            log(`Restart failed: ${message}`);
            vscode.window.showErrorMessage('X Language Server restart failed');
        }
    }));
    context.subscriptions.push(vscode.commands.registerCommand('xlang.checkFile', async () => {
        const editor = vscode.window.activeTextEditor;
        if (editor && editor.document.languageId === 'x') {
            await client?.sendNotification('textDocument/didSave', {
                textDocument: { uri: editor.document.uri.toString() }
            });
            vscode.window.showInformationMessage('Type check triggered');
        }
    }));
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
        if (e.affectsConfiguration('xlang')) {
            if (e.affectsConfiguration('xlang.pythonPath') || e.affectsConfiguration('xlang.serverPath')) {
                void vscode.window.showInformationMessage('Restart the X Language Server to apply the new path.');
                return;
            }
            void client?.sendNotification('workspace/didChangeConfiguration', {
                settings: readSettings()
            });
        }
    }));
    context.subscriptions.push(outputChannel);
}
function deactivate() {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
//# sourceMappingURL=extension.js.map