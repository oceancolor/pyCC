# 原始 TS: utils/powershell/parser.ts
"""
PowerShell AST 解析器

通过调用 pwsh -EncodedCommand 解析 PowerShell 命令，
返回结构化的 AST 信息，用于安全性分析。

移植自 utils/powershell/parser.ts (1804 行)
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

# ---------------------------------------------------------------------------
# Public types describing parsed output returned to callers.
# These map to System.Management.Automation.Language AST classes.
# ---------------------------------------------------------------------------

PipelineElementType = Literal['CommandAst', 'CommandExpressionAst', 'ParenExpressionAst']

CommandElementType = Literal[
    'ScriptBlock', 'SubExpression', 'ExpandableString',
    'MemberInvocation', 'Variable', 'StringConstant', 'Parameter', 'Other'
]

StatementType = Literal[
    'PipelineAst', 'PipelineChainAst', 'AssignmentStatementAst',
    'IfStatementAst', 'ForStatementAst', 'ForEachStatementAst',
    'WhileStatementAst', 'DoWhileStatementAst', 'DoUntilStatementAst',
    'SwitchStatementAst', 'TryStatementAst', 'TrapStatementAst',
    'FunctionDefinitionAst', 'DataStatementAst', 'UnknownStatementAst'
]


class CommandElementChild(TypedDict):
    """A child node of a command element (one level deep)."""
    type: str  # CommandElementType
    text: str


class ParsedRedirection(TypedDict):
    """A redirection found in the command."""
    operator: str  # '>' | '>>' | '2>' | '2>>' | '*>' | '*>>' | '2>&1'
    target: str
    isMerging: bool


class ParsedCommandElement(TypedDict, total=False):
    """A command invocation within a pipeline segment."""
    name: str
    nameType: str  # 'cmdlet' | 'application' | 'unknown'
    elementType: str  # PipelineElementType
    args: List[str]
    text: str
    elementTypes: List[str]  # List[CommandElementType]
    children: List[Optional[List[CommandElementChild]]]
    redirections: List[ParsedRedirection]


class SecurityPatterns(TypedDict, total=False):
    hasMemberInvocations: bool
    hasSubExpressions: bool
    hasExpandableStrings: bool
    hasScriptBlocks: bool


class ParsedStatement(TypedDict, total=False):
    """A parsed statement from PowerShell."""
    statementType: str  # StatementType
    commands: List[ParsedCommandElement]
    redirections: List[ParsedRedirection]
    text: str
    nestedCommands: List[ParsedCommandElement]
    securityPatterns: SecurityPatterns


class ParsedVariable(TypedDict):
    """A variable reference found in the command."""
    path: str
    isSplatted: bool


class ParseError(TypedDict):
    """A parse error from PowerShell's parser."""
    message: str
    errorId: str


class ParsedPowerShellCommand(TypedDict, total=False):
    """The complete parsed result from the PowerShell AST parser."""
    valid: bool
    errors: List[ParseError]
    statements: List[ParsedStatement]
    variables: List[ParsedVariable]
    hasStopParsing: bool
    originalCommand: str
    typeLiterals: List[str]
    hasUsingStatements: bool
    hasScriptRequirements: bool


# ---------------------------------------------------------------------------
# Raw types describing PS script JSON output (exported for testing)
# ---------------------------------------------------------------------------

class RawCommandElement(TypedDict, total=False):
    type: str
    text: str
    value: str
    expressionType: str
    children: List[Dict[str, str]]


class RawRedirection(TypedDict, total=False):
    type: str
    append: bool
    fromStream: str
    locationText: str


class RawPipelineElement(TypedDict, total=False):
    type: str
    text: str
    commandElements: List[RawCommandElement]
    redirections: List[RawRedirection]
    expressionType: str


class RawStatement(TypedDict, total=False):
    type: str
    text: str
    elements: List[RawPipelineElement]
    nestedCommands: List[RawPipelineElement]
    redirections: List[RawRedirection]
    securityPatterns: SecurityPatterns


# ---------------------------------------------------------------------------
# PowerShell parse script body (canonical copy — no separate .ps1 file)
# ---------------------------------------------------------------------------

PARSE_SCRIPT_BODY = r"""
if (-not $EncodedCommand) {
    Write-Output '{"valid":false,"errors":[{"message":"No command provided","errorId":"NoInput"}],"statements":[],"variables":[],"hasStopParsing":false,"originalCommand":""}'
    exit 0
}

$Command = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($EncodedCommand))

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput(
    $Command,
    [ref]$tokens,
    [ref]$parseErrors
)

$allVariables = [System.Collections.ArrayList]::new()

function Get-RawCommandElements {
    param([System.Management.Automation.Language.CommandAst]$CmdAst)
    $elems = [System.Collections.ArrayList]::new()
    foreach ($ce in $CmdAst.CommandElements) {
        $ceData = @{ type = $ce.GetType().Name; text = $ce.Extent.Text }
        if ($ce.PSObject.Properties['Value'] -and $null -ne $ce.Value -and $ce.Value -is [string]) {
            $ceData.value = $ce.Value
        }
        if ($ce -is [System.Management.Automation.Language.CommandExpressionAst]) {
            $ceData.expressionType = $ce.Expression.GetType().Name
        }
        $a=$ce.Argument;if($a){$ceData.children=@(@{type=$a.GetType().Name;text=$a.Extent.Text})}
        [void]$elems.Add($ceData)
    }
    return $elems
}

function Get-RawRedirections {
    param($Redirections)
    $result = [System.Collections.ArrayList]::new()
    foreach ($redir in $Redirections) {
        $redirData = @{ type = $redir.GetType().Name }
        if ($redir -is [System.Management.Automation.Language.FileRedirectionAst]) {
            $redirData.append = [bool]$redir.Append
            $redirData.fromStream = $redir.FromStream.ToString()
            $redirData.locationText = $redir.Location.Extent.Text
        }
        [void]$result.Add($redirData)
    }
    return $result
}

function Get-SecurityPatterns($A) {
    $p = @{}
    foreach ($n in $A.FindAll({ param($x)
        $x -is [System.Management.Automation.Language.MemberExpressionAst] -or
        $x -is [System.Management.Automation.Language.SubExpressionAst] -or
        $x -is [System.Management.Automation.Language.ArrayExpressionAst] -or
        $x -is [System.Management.Automation.Language.ExpandableStringExpressionAst] -or
        $x -is [System.Management.Automation.Language.ScriptBlockExpressionAst] -or
        $x -is [System.Management.Automation.Language.ParenExpressionAst]
    }, $true)) { switch ($n.GetType().Name) {
        'InvokeMemberExpressionAst' { $p.hasMemberInvocations = $true }
        'MemberExpressionAst' { $p.hasMemberInvocations = $true }
        'SubExpressionAst' { $p.hasSubExpressions = $true }
        'ArrayExpressionAst' { $p.hasSubExpressions = $true }
        'ParenExpressionAst' { $p.hasSubExpressions = $true }
        'ExpandableStringExpressionAst' { $p.hasExpandableStrings = $true }
        'ScriptBlockExpressionAst' { $p.hasScriptBlocks = $true }
    }}
    if ($p.Count -gt 0) { return $p }
    return $null
}

$varExprs = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.VariableExpressionAst] }, $true)
foreach ($v in $varExprs) {
    [void]$allVariables.Add(@{
        path = $v.VariablePath.ToString()
        isSplatted = [bool]$v.Splatted
    })
}

$typeLiterals = [System.Collections.ArrayList]::new()
foreach ($t in $ast.FindAll({ param($n)
    $n -is [System.Management.Automation.Language.TypeExpressionAst] -or
    $n -is [System.Management.Automation.Language.TypeConstraintAst]
}, $true)) { [void]$typeLiterals.Add($t.TypeName.FullName) }

$hasStopParsing = $false
$tk = [System.Management.Automation.Language.TokenKind]
foreach ($tok in $tokens) {
    if ($tok.Kind -eq $tk::MinusMinus) { $hasStopParsing = $true; break }
    if ($tok.Kind -eq $tk::Generic -and ($tok.Text -replace '[\u2013\u2014\u2015]','-') -eq '--%') {
        $hasStopParsing = $true; break
    }
}

$statements = [System.Collections.ArrayList]::new()

function Process-BlockStatements {
    param($Block)
    if (-not $Block) { return }

    foreach ($stmt in $Block.Statements) {
        $statement = @{
            type = $stmt.GetType().Name
            text = $stmt.Extent.Text
        }

        if ($stmt -is [System.Management.Automation.Language.PipelineAst]) {
            $elements = [System.Collections.ArrayList]::new()
            foreach ($element in $stmt.PipelineElements) {
                $elemData = @{
                    type = $element.GetType().Name
                    text = $element.Extent.Text
                }

                if ($element -is [System.Management.Automation.Language.CommandAst]) {
                    $elemData.commandElements = @(Get-RawCommandElements -CmdAst $element)
                    $elemData.redirections = @(Get-RawRedirections -Redirections $element.Redirections)
                } elseif ($element -is [System.Management.Automation.Language.CommandExpressionAst]) {
                    $elemData.expressionType = $element.Expression.GetType().Name
                    $elemData.redirections = @(Get-RawRedirections -Redirections $element.Redirections)
                }

                [void]$elements.Add($elemData)
            }
            $statement.elements = @($elements)

            $allNestedCmds = $stmt.FindAll(
                { param($node) $node -is [System.Management.Automation.Language.CommandAst] },
                $true
            )
            $nestedCmds = [System.Collections.ArrayList]::new()
            foreach ($cmd in $allNestedCmds) {
                if ($cmd.Parent -eq $stmt) { continue }
                $nested = @{
                    type = $cmd.GetType().Name
                    text = $cmd.Extent.Text
                    commandElements = @(Get-RawCommandElements -CmdAst $cmd)
                    redirections = @(Get-RawRedirections -Redirections $cmd.Redirections)
                }
                [void]$nestedCmds.Add($nested)
            }
            if ($nestedCmds.Count -gt 0) {
                $statement.nestedCommands = @($nestedCmds)
            }
            $r = $stmt.FindAll({param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst]}, $true)
            if ($r.Count -gt 0) {
                $rr = @(Get-RawRedirections -Redirections $r)
                $statement.redirections = if ($statement.redirections) { @($statement.redirections) + $rr } else { $rr }
            }
        } else {
            $nestedCmdAsts = $stmt.FindAll(
                { param($node) $node -is [System.Management.Automation.Language.CommandAst] },
                $true
            )
            $nested = [System.Collections.ArrayList]::new()
            foreach ($cmd in $nestedCmdAsts) {
                [void]$nested.Add(@{
                    type = 'CommandAst'
                    text = $cmd.Extent.Text
                    commandElements = @(Get-RawCommandElements -CmdAst $cmd)
                    redirections = @(Get-RawRedirections -Redirections $cmd.Redirections)
                })
            }
            if ($nested.Count -gt 0) {
                $statement.nestedCommands = @($nested)
            }
            $r = $stmt.FindAll({param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst]}, $true)
            if ($r.Count -gt 0) { $statement.redirections = @(Get-RawRedirections -Redirections $r) }
        }

        $sp = Get-SecurityPatterns $stmt
        if ($sp) { $statement.securityPatterns = $sp }

        [void]$statements.Add($statement)
    }

    if ($Block.Traps) {
        foreach ($trap in $Block.Traps) {
            $statement = @{
                type = 'TrapStatementAst'
                text = $trap.Extent.Text
            }
            $nestedCmdAsts = $trap.FindAll(
                { param($node) $node -is [System.Management.Automation.Language.CommandAst] },
                $true
            )
            $nestedCmds = [System.Collections.ArrayList]::new()
            foreach ($cmd in $nestedCmdAsts) {
                $nested = @{
                    type = $cmd.GetType().Name
                    text = $cmd.Extent.Text
                    commandElements = @(Get-RawCommandElements -CmdAst $cmd)
                    redirections = @(Get-RawRedirections -Redirections $cmd.Redirections)
                }
                [void]$nestedCmds.Add($nested)
            }
            if ($nestedCmds.Count -gt 0) {
                $statement.nestedCommands = @($nestedCmds)
            }
            $r = $trap.FindAll({param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst]}, $true)
            if ($r.Count -gt 0) { $statement.redirections = @(Get-RawRedirections -Redirections $r) }
            $sp = Get-SecurityPatterns $trap
            if ($sp) { $statement.securityPatterns = $sp }
            [void]$statements.Add($statement)
        }
    }
}

Process-BlockStatements -Block $ast.BeginBlock
Process-BlockStatements -Block $ast.ProcessBlock
Process-BlockStatements -Block $ast.EndBlock
Process-BlockStatements -Block $ast.CleanBlock
Process-BlockStatements -Block $ast.DynamicParamBlock

if ($ast.ParamBlock) {
  $pb = $ast.ParamBlock
  $pn = [System.Collections.ArrayList]::new()
  foreach ($c in $pb.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]}, $true)) {
    [void]$pn.Add(@{type='CommandAst';text=$c.Extent.Text;commandElements=@(Get-RawCommandElements -CmdAst $c);redirections=@(Get-RawRedirections -Redirections $c.Redirections)})
  }
  $pr = $pb.FindAll({param($n) $n -is [System.Management.Automation.Language.FileRedirectionAst]}, $true)
  $ps = Get-SecurityPatterns $pb
  if ($pn.Count -gt 0 -or $pr.Count -gt 0 -or $ps) {
    $st = @{type='ParamBlockAst';text=$pb.Extent.Text}
    if ($pn.Count -gt 0) { $st.nestedCommands = @($pn) }
    if ($pr.Count -gt 0) { $st.redirections = @(Get-RawRedirections -Redirections $pr) }
    if ($ps) { $st.securityPatterns = $ps }
    [void]$statements.Add($st)
  }
}

$hasUsingStatements = $ast.UsingStatements -and $ast.UsingStatements.Count -gt 0
$hasScriptRequirements = $ast.ScriptRequirements -ne $null

$output = @{
    valid = ($parseErrors.Count -eq 0)
    errors = @($parseErrors | ForEach-Object {
        @{
            message = $_.Message
            errorId = $_.ErrorId
        }
    })
    statements = @($statements)
    variables = @($allVariables)
    hasStopParsing = $hasStopParsing
    originalCommand = $Command
    typeLiterals = @($typeLiterals)
    hasUsingStatements = [bool]$hasUsingStatements
    hasScriptRequirements = [bool]$hasScriptRequirements
}

$output | ConvertTo-Json -Depth 10 -Compress
"""

# ---------------------------------------------------------------------------
# Windows argv budget calculation
# ---------------------------------------------------------------------------

# Windows CreateProcess has a 32,767 char command-line limit.
WINDOWS_ARGV_CAP = 32_767
FIXED_ARGV_OVERHEAD = 200
ENCODED_CMD_WRAPPER = len("$EncodedCommand = ''\n")
SAFETY_MARGIN = 100

SCRIPT_CHARS_BUDGET = ((WINDOWS_ARGV_CAP - FIXED_ARGV_OVERHEAD) * 3) / 8
CMD_B64_BUDGET = SCRIPT_CHARS_BUDGET - len(PARSE_SCRIPT_BODY) - ENCODED_CMD_WRAPPER

# Unit: UTF-8 BYTES. Compare against len(cmd.encode('utf-8')), not len(cmd).
WINDOWS_MAX_COMMAND_LENGTH = max(0, int((CMD_B64_BUDGET * 3) / 4) - SAFETY_MARGIN)

# Pre-existing value, known to work on Unix.
UNIX_MAX_COMMAND_LENGTH = 4_500

MAX_COMMAND_LENGTH = (
    WINDOWS_MAX_COMMAND_LENGTH if platform.system() == 'Windows'
    else UNIX_MAX_COMMAND_LENGTH
)

# ---------------------------------------------------------------------------
# Default parse timeout
# ---------------------------------------------------------------------------

DEFAULT_PARSE_TIMEOUT_MS = 5_000


def get_parse_timeout_ms() -> int:
    """Read timeout from env, fallback to default."""
    env = os.environ.get('CLAUDE_CODE_PWSH_PARSE_TIMEOUT_MS')
    if env:
        try:
            parsed = int(env)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_PARSE_TIMEOUT_MS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def to_utf16le_base64(text: str) -> str:
    """Base64-encode a string as UTF-16LE (required by PowerShell's -EncodedCommand)."""
    return base64.b64encode(text.encode('utf-16-le')).decode('ascii')


def build_parse_script(command: str) -> str:
    """Build the full PowerShell script that parses a command."""
    encoded = base64.b64encode(command.encode('utf-8')).decode('ascii')
    return f"$EncodedCommand = '{encoded}'\n{PARSE_SCRIPT_BODY}"


def ensure_array(value: Any) -> list:
    """Ensure a value is a list (PowerShell 5.1 may unwrap single-element arrays)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ---------------------------------------------------------------------------
# Mapping / transformation helpers (exported for testing)
# ---------------------------------------------------------------------------

def map_statement_type(raw_type: str) -> str:
    """Map raw .NET AST type name to our StatementType."""
    mapping = {
        'PipelineAst': 'PipelineAst',
        'PipelineChainAst': 'PipelineChainAst',
        'AssignmentStatementAst': 'AssignmentStatementAst',
        'IfStatementAst': 'IfStatementAst',
        'ForStatementAst': 'ForStatementAst',
        'ForEachStatementAst': 'ForEachStatementAst',
        'WhileStatementAst': 'WhileStatementAst',
        'DoWhileStatementAst': 'DoWhileStatementAst',
        'DoUntilStatementAst': 'DoUntilStatementAst',
        'SwitchStatementAst': 'SwitchStatementAst',
        'TryStatementAst': 'TryStatementAst',
        'TrapStatementAst': 'TrapStatementAst',
        'FunctionDefinitionAst': 'FunctionDefinitionAst',
        'DataStatementAst': 'DataStatementAst',
    }
    return mapping.get(raw_type, 'UnknownStatementAst')


def map_element_type(raw_type: str, expression_type: Optional[str] = None) -> str:
    """Map raw .NET AST type name to our CommandElementType."""
    mapping = {
        'ScriptBlockExpressionAst': 'ScriptBlock',
        'SubExpressionAst': 'SubExpression',
        'ArrayExpressionAst': 'SubExpression',
        'ExpandableStringExpressionAst': 'ExpandableString',
        'InvokeMemberExpressionAst': 'MemberInvocation',
        'MemberExpressionAst': 'MemberInvocation',
        'VariableExpressionAst': 'Variable',
        'StringConstantExpressionAst': 'StringConstant',
        'ConstantExpressionAst': 'StringConstant',
        'CommandParameterAst': 'Parameter',
        'ParenExpressionAst': 'SubExpression',
    }
    if raw_type == 'CommandExpressionAst':
        if expression_type:
            return map_element_type(expression_type)
        return 'Other'
    return mapping.get(raw_type, 'Other')


def classify_command_name(name: str) -> str:
    """Classify command name as 'cmdlet', 'application', or 'unknown'."""
    if re.match(r'^[A-Za-z]+-[A-Za-z][A-Za-z0-9_]*$', name):
        return 'cmdlet'
    if re.search(r'[.\\/]', name):
        return 'application'
    return 'unknown'


def strip_module_prefix(name: str) -> str:
    """Strip module prefix from command name (e.g. 'Module\\Invoke-Expression' -> 'Invoke-Expression')."""
    idx = name.rfind('\\')
    if idx < 0:
        return name
    # Don't strip file paths
    if (re.match(r'^[A-Za-z]:', name) or
            name.startswith('\\\\') or
            name.startswith('.\\') or
            name.startswith('..\\')):
        return name
    return name[idx + 1:]


def transform_redirection(raw: RawRedirection) -> ParsedRedirection:
    """Map raw redirection to ParsedRedirection."""
    if raw.get('type') == 'MergingRedirectionAst':
        return ParsedRedirection(operator='2>&1', target='', isMerging=True)

    append = raw.get('append', False)
    from_stream = raw.get('fromStream', 'Output')

    if append:
        op_map = {'Error': '2>>', 'All': '*>>'}
        operator = op_map.get(from_stream, '>>')
    else:
        op_map = {'Error': '2>', 'All': '*>'}
        operator = op_map.get(from_stream, '>')

    return ParsedRedirection(operator=operator, target=raw.get('locationText', ''), isMerging=False)


def transform_command_ast(raw: RawPipelineElement) -> ParsedCommandElement:
    """Transform a raw CommandAst pipeline element into ParsedCommandElement."""
    cmd_elements = ensure_array(raw.get('commandElements'))
    name = ''
    args: List[str] = []
    element_types: List[str] = []
    children: List[Optional[List[CommandElementChild]]] = []
    has_children = False
    name_type = 'unknown'

    if cmd_elements:
        first = cmd_elements[0]
        is_first_string_literal = first.get('type') in (
            'StringConstantExpressionAst', 'ExpandableStringExpressionAst')
        if is_first_string_literal and isinstance(first.get('value'), str):
            raw_name_unstripped = first['value']
        else:
            raw_name_unstripped = first.get('text', '')

        # Strip surrounding quotes
        raw_name = raw_name_unstripped.strip("'\"")

        # SECURITY: non-ASCII in cmdlet position → force 'application'
        if re.search(r'[\u0080-\uFFFF]', raw_name):
            name_type = 'application'
        else:
            name_type = classify_command_name(raw_name)

        name = strip_module_prefix(raw_name)
        element_types.append(map_element_type(
            first.get('type', ''), first.get('expressionType')))

        for ce in cmd_elements[1:]:
            is_string_literal = ce.get('type') in (
                'StringConstantExpressionAst', 'ExpandableStringExpressionAst')
            if is_string_literal and ce.get('value') is not None:
                args.append(ce['value'])
            else:
                args.append(ce.get('text', ''))
            element_types.append(map_element_type(
                ce.get('type', ''), ce.get('expressionType')))

            raw_children = ensure_array(ce.get('children'))
            if raw_children:
                has_children = True
                children.append([
                    CommandElementChild(
                        type=map_element_type(c.get('type', '')),
                        text=c.get('text', '')
                    )
                    for c in raw_children
                ])
            else:
                children.append(None)

    result: ParsedCommandElement = {
        'name': name,
        'nameType': name_type,
        'elementType': 'CommandAst',
        'args': args,
        'text': raw.get('text', ''),
        'elementTypes': element_types,
    }
    if has_children:
        result['children'] = children

    raw_redirs = ensure_array(raw.get('redirections'))
    if raw_redirs:
        result['redirections'] = [transform_redirection(r) for r in raw_redirs]

    return result


def transform_expression_element(raw: RawPipelineElement) -> ParsedCommandElement:
    """Transform a non-CommandAst pipeline element into ParsedCommandElement."""
    raw_type = raw.get('type', '')
    element_type: str = ('ParenExpressionAst'
                         if raw_type == 'ParenExpressionAst'
                         else 'CommandExpressionAst')
    element_types = [map_element_type(raw_type, raw.get('expressionType'))]
    return ParsedCommandElement(
        name=raw.get('text', ''),
        nameType='unknown',
        elementType=element_type,
        args=[],
        text=raw.get('text', ''),
        elementTypes=element_types,
    )


def transform_statement(raw: RawStatement) -> ParsedStatement:
    """Transform a raw statement into ParsedStatement."""
    statement_type = map_statement_type(raw.get('type', ''))
    commands: List[ParsedCommandElement] = []
    redirections: List[ParsedRedirection] = []

    if raw.get('elements') is not None:
        # PipelineAst: walk pipeline elements
        for elem in ensure_array(raw.get('elements')):
            if elem.get('type') == 'CommandAst':
                commands.append(transform_command_ast(elem))
                for redir in ensure_array(elem.get('redirections')):
                    redirections.append(transform_redirection(redir))
            else:
                commands.append(transform_expression_element(elem))
                for redir in ensure_array(elem.get('redirections')):
                    redirections.append(transform_redirection(redir))
    else:
        # Non-pipeline: redirections at statement level
        for redir in ensure_array(raw.get('redirections')):
            redirections.append(transform_redirection(redir))

    stmt: ParsedStatement = {
        'statementType': statement_type,
        'commands': commands,
        'redirections': redirections,
        'text': raw.get('text', ''),
    }

    # Nested commands (control-flow bodies)
    if raw.get('nestedCommands'):
        nested: List[ParsedCommandElement] = []
        for nc in ensure_array(raw['nestedCommands']):
            if nc.get('type') == 'CommandAst':
                nested.append(transform_command_ast(nc))
            else:
                nested.append(transform_expression_element(nc))
        stmt['nestedCommands'] = nested

    # Security patterns
    if raw.get('securityPatterns'):
        stmt['securityPatterns'] = raw['securityPatterns']

    return stmt


def transform_parsed_output(raw: dict) -> ParsedPowerShellCommand:
    """Transform the raw JSON output from pwsh into a ParsedPowerShellCommand."""
    statements = [transform_statement(s) for s in ensure_array(raw.get('statements'))]
    variables = [
        ParsedVariable(path=v.get('path', ''), isSplatted=bool(v.get('isSplatted', False)))
        for v in ensure_array(raw.get('variables'))
    ]
    errors = [
        ParseError(message=e.get('message', ''), errorId=e.get('errorId', ''))
        for e in ensure_array(raw.get('errors'))
    ]

    result = ParsedPowerShellCommand(
        valid=bool(raw.get('valid', False)),
        errors=errors,
        statements=statements,
        variables=variables,
        hasStopParsing=bool(raw.get('hasStopParsing', False)),
        originalCommand=raw.get('originalCommand', ''),
    )
    if raw.get('typeLiterals') is not None:
        result['typeLiterals'] = ensure_array(raw['typeLiterals'])
    if raw.get('hasUsingStatements') is not None:
        result['hasUsingStatements'] = bool(raw['hasUsingStatements'])
    if raw.get('hasScriptRequirements') is not None:
        result['hasScriptRequirements'] = bool(raw['hasScriptRequirements'])
    return result


# ---------------------------------------------------------------------------
# Invalid result helpers
# ---------------------------------------------------------------------------

_INVALID_RESULT_BASE: dict = {
    'valid': False,
    'statements': [],
    'variables': [],
    'hasStopParsing': False,
}


def make_invalid_result(command: str, message: str, error_id: str) -> ParsedPowerShellCommand:
    return ParsedPowerShellCommand(
        **_INVALID_RESULT_BASE,
        errors=[ParseError(message=message, errorId=error_id)],
        originalCommand=command,
    )


# ---------------------------------------------------------------------------
# pwsh detection (simple memoized)
# ---------------------------------------------------------------------------

_pwsh_path_cache: Optional[str] = None
_pwsh_path_checked = False


def _get_cached_powershell_path() -> Optional[str]:
    """Return path to pwsh (PowerShell Core) if available."""
    global _pwsh_path_cache, _pwsh_path_checked
    if _pwsh_path_checked:
        return _pwsh_path_cache
    _pwsh_path_checked = True
    import shutil
    path = shutil.which('pwsh')
    if path is None and platform.system() == 'Windows':
        # Try common locations on Windows
        for candidate in [
            r'C:\Program Files\PowerShell\7\pwsh.exe',
            r'C:\Program Files\PowerShell\6\pwsh.exe',
        ]:
            if os.path.isfile(candidate):
                path = candidate
                break
    _pwsh_path_cache = path
    return path


def can_spawn_parse_script() -> bool:
    """Return True if pwsh is available for parsing."""
    return _get_cached_powershell_path() is not None


# ---------------------------------------------------------------------------
# Core parse implementation
# ---------------------------------------------------------------------------

def _parse_powershell_command_impl(command: str) -> ParsedPowerShellCommand:
    """
    Synchronous implementation: spawn pwsh and parse the command.
    Returns a ParsedPowerShellCommand.
    """
    pwsh_path = _get_cached_powershell_path()
    if not pwsh_path:
        return make_invalid_result(command, 'pwsh not found', 'PwshNotFound')

    # Length gate (UTF-8 bytes)
    cmd_bytes = len(command.encode('utf-8'))
    if cmd_bytes > MAX_COMMAND_LENGTH:
        return make_invalid_result(
            command,
            f'Command too long for PowerShell AST parser ({cmd_bytes} UTF-8 bytes, max {MAX_COMMAND_LENGTH})',
            'CommandTooLong',
        )

    script = build_parse_script(command)
    encoded_script = to_utf16le_base64(script)
    args = [pwsh_path, '-NoProfile', '-NonInteractive', '-NoLogo',
            '-EncodedCommand', encoded_script]

    parse_timeout_ms = get_parse_timeout_ms()
    stdout = ''
    stderr = ''
    code: Optional[int] = None
    timed_out = False

    for attempt in range(2):
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=parse_timeout_ms / 1000,
            )
            stdout = result.stdout
            stderr = result.stderr
            code = result.returncode
            timed_out = False
            break
        except subprocess.TimeoutExpired:
            if attempt == 0:
                timed_out = True
                continue
            # second timeout
            return make_invalid_result(command, 'pwsh parse timed out', 'PwshTimeout')
        except FileNotFoundError:
            return make_invalid_result(command, 'pwsh not found', 'PwshNotFound')
        except Exception as e:
            return make_invalid_result(command, f'pwsh spawn failed: {e}', 'PwshSpawnError')

    if timed_out:
        return make_invalid_result(command, 'pwsh parse timed out', 'PwshTimeout')

    if code is not None and code != 0:
        return make_invalid_result(
            command,
            f'pwsh exited with code {code}: {stderr.strip()}',
            'PwshNonZeroExit',
        )

    stdout_stripped = stdout.strip()
    if not stdout_stripped:
        return make_invalid_result(command, 'pwsh produced no output', 'EmptyOutput')

    try:
        raw = json.loads(stdout_stripped)
    except json.JSONDecodeError as e:
        return make_invalid_result(command, f'Failed to parse pwsh output: {e}', 'JsonParseError')

    return transform_parsed_output(raw)


def parse_powershell_command(command: str) -> ParsedPowerShellCommand:
    """
    Parse a PowerShell command synchronously using pwsh.

    Args:
        command: The PowerShell command string to parse.
    Returns:
        ParsedPowerShellCommand with AST information.
    """
    return _parse_powershell_command_impl(command)


async def parse_powershell_command_async(command: str) -> ParsedPowerShellCommand:
    """
    Parse a PowerShell command asynchronously using pwsh.

    Args:
        command: The PowerShell command string to parse.
    Returns:
        ParsedPowerShellCommand with AST information.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _parse_powershell_command_impl, command)


# ---------------------------------------------------------------------------
# Derived helpers for consumers
# ---------------------------------------------------------------------------

class SecurityFlags(TypedDict, total=False):
    """Security-relevant flags derived from the parsed AST."""
    has_nested_commands: bool
    has_member_invocations: bool
    has_sub_expressions: bool
    has_expandable_strings: bool
    has_script_blocks: bool
    has_redirections: bool
    has_stop_parsing: bool
    has_using_statements: bool
    has_script_requirements: bool
    has_type_literals: bool


def get_security_flags(parsed: ParsedPowerShellCommand) -> SecurityFlags:
    """Extract security-relevant flags from a parsed PowerShell command."""
    flags = SecurityFlags()

    for stmt in parsed.get('statements', []):
        if stmt.get('nestedCommands'):
            flags['has_nested_commands'] = True
        sp = stmt.get('securityPatterns') or {}
        if sp.get('hasMemberInvocations'):
            flags['has_member_invocations'] = True
        if sp.get('hasSubExpressions'):
            flags['has_sub_expressions'] = True
        if sp.get('hasExpandableStrings'):
            flags['has_expandable_strings'] = True
        if sp.get('hasScriptBlocks'):
            flags['has_script_blocks'] = True
        if stmt.get('redirections'):
            flags['has_redirections'] = True

    if parsed.get('hasStopParsing'):
        flags['has_stop_parsing'] = True
    if parsed.get('hasUsingStatements'):
        flags['has_using_statements'] = True
    if parsed.get('hasScriptRequirements'):
        flags['has_script_requirements'] = True
    if parsed.get('typeLiterals'):
        flags['has_type_literals'] = True

    return flags


def get_all_commands(parsed: ParsedPowerShellCommand) -> List[ParsedCommandElement]:
    """Get all commands (including nested) from a parsed result."""
    commands: List[ParsedCommandElement] = []
    for stmt in parsed.get('statements', []):
        commands.extend(stmt.get('commands', []))
        commands.extend(stmt.get('nestedCommands', []))
    return commands


def get_file_redirections(parsed: ParsedPowerShellCommand) -> List[ParsedRedirection]:
    """Get all file redirections across all statements."""
    result: List[ParsedRedirection] = []
    for stmt in parsed.get('statements', []):
        for redir in stmt.get('redirections', []):
            if not redir.get('isMerging'):
                result.append(redir)
    return result


def is_simple_pipeline(parsed: ParsedPowerShellCommand) -> bool:
    """Return True if the parsed result is a simple pipeline with no control flow."""
    statements = parsed.get('statements', [])
    if len(statements) != 1:
        return False
    stmt = statements[0]
    return (stmt.get('statementType') == 'PipelineAst' and
            not stmt.get('nestedCommands'))


def is_specific_command(parsed: ParsedPowerShellCommand, name: str) -> bool:
    """Return True if the parsed result is a single invocation of the named command."""
    if not is_simple_pipeline(parsed):
        return False
    stmt = parsed['statements'][0]
    cmds = stmt.get('commands', [])
    if len(cmds) != 1:
        return False
    return cmds[0].get('name', '').lower() == name.lower()
