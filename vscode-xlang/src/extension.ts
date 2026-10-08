import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { spawnSync } from 'child_process';
import { LanguageClient, LanguageClientOptions, ServerOptions, TransportKind } from 'vscode-languageclient/node';

let client: LanguageClient | undefined;
let outputChannel: vscode.LogOutputChannel | undefined;

function log(message: string): void {
    outputChannel?.appendLine(message);
    console.log(`[xlang] ${message}`);
}

function canImport(python: string, module: string): boolean {
    try {
        const result = spawnSync(python, ['-c', `import ${module}`], {
            timeout: 5000,
            windowsHide: true
        });
        return result.status === 0;
    } catch {
        return false;
    }
}

function isExecutable(candidate: string): boolean {
    if (candidate.includes(path.sep) || path.isAbsolute(candidate)) {
        return fs.existsSync(candidate);
    }
    return true;
}

function resolvePython(workspaceFolders: readonly vscode.WorkspaceFolder[] | undefined): string {
    const configured = (vscode.workspace.getConfiguration('xlang').get<string>('pythonPath') ?? '').trim();
    if (configured) {
        return configured;
    }

    const candidates: string[] = [];
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

function resolveServerModule(context: vscode.ExtensionContext): string {
    const configured = (vscode.workspace.getConfiguration('xlang').get<string>('serverPath') ?? '').trim();
    if (configured) {
        return configured;
    }
    return context.asAbsolutePath(path.join('server', 'server.py'));
}

function readSettings(): { enableTypeChecking: boolean; strictTyping: boolean } {
    const config = vscode.workspace.getConfiguration('xlang');
    return {
        enableTypeChecking: config.get<boolean>('enableTypeChecking', true),
        strictTyping: config.get<boolean>('strictTyping', false)
    };
}

function buildServerEnv(workspaceFolders: readonly vscode.WorkspaceFolder[] | undefined): NodeJS.ProcessEnv {
    const env: NodeJS.ProcessEnv = { ...process.env };
    const roots = (workspaceFolders ?? []).map(folder => folder.uri.fsPath);
    if (roots.length > 0) {
        env.PYTHONPATH = env.PYTHONPATH
            ? [...roots, env.PYTHONPATH].join(path.delimiter)
            : roots.join(path.delimiter);
    }
    return env;
}

export function activate(context: vscode.ExtensionContext) {
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

    const serverOptions: ServerOptions = {
        run: {
            command: python,
            args: [serverModule],
            transport: TransportKind.stdio,
            options: { env, cwd }
        },
        debug: {
            command: python,
            args: [serverModule],
            transport: TransportKind.stdio,
            options: { env, cwd }
        }
    };

    const clientOptions: LanguageClientOptions = {
        documentSelector: [{ scheme: 'file', language: 'x' }],
        synchronize: {
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.{x,toml}')
        },
        initializationOptions: readSettings(),
        outputChannel
    };

    client = new LanguageClient(
        'xlang',
        'X Language Server',
        serverOptions,
        clientOptions
    );

    client.start().then(
        () => log('X Language Server started'),
        (error: unknown) => {
            const message = error instanceof Error ? error.message : String(error);
            log(`X Language Server failed to start: ${message}`);
            vscode.window.showErrorMessage(
                `X Language Server failed to start. See the "X Language" output channel for details.`
            );
        }
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('xlang.restartServer', async () => {
            if (!client) {
                return;
            }
            try {
                await client.stop();
                await client.start();
                vscode.window.showInformationMessage('X Language Server restarted');
            } catch (error) {
                const message = error instanceof Error ? error.message : String(error);
                log(`Restart failed: ${message}`);
                vscode.window.showErrorMessage('X Language Server restart failed');
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('xlang.checkFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (editor && editor.document.languageId === 'x') {
                await client?.sendNotification('textDocument/didSave', {
                    textDocument: { uri: editor.document.uri.toString() }
                });
                vscode.window.showInformationMessage('Type check triggered');
            }
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(e => {
            if (e.affectsConfiguration('xlang')) {
            if (e.affectsConfiguration('xlang.pythonPath') || e.affectsConfiguration('xlang.serverPath')) {
                void vscode.window.showInformationMessage(
                    'Restart the X Language Server to apply the new path.'
                );
                return;
            }
            void client?.sendNotification('workspace/didChangeConfiguration', {
                settings: readSettings()
            });
            }
        })
    );

    context.subscriptions.push(outputChannel);
}

export function deactivate(): Thenable<void> | undefined {
    if (!client) {
        return undefined;
    }
    return client.stop();
}
