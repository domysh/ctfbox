import code
import sys
import readline

class EnhancedInteractiveConsole(code.InteractiveConsole):
    def __init__(self, locals=None, filename="<console>"):
        super().__init__(locals, filename)
        self.input_lines = []
        self.multiline_input = False
        
    def get_input(self, prompt=">>> "):
        """Get input from the user, supporting multiline input."""
        line = input(prompt)
        
        # Check if we're starting or continuing multiline input
        if line.endswith("\\"):
            self.multiline_input = True
            self.input_lines.append(line[:-1])  # Remove the trailing backslash
            return self.get_multiline_input()
        
        return line
    
    def get_multiline_input(self):
        """Handle multiline input with custom continuation prompt."""
        while self.multiline_input:
            try:
                line = input("... ")
                if line.endswith("\\"):
                    self.input_lines.append(line[:-1])  # Remove the trailing backslash
                else:
                    self.input_lines.append(line)
                    self.multiline_input = False
            except EOFError:
                self.multiline_input = False
        
        # Join all input lines and reset
        result = "\n".join(self.input_lines)
        self.input_lines = []
        return result
    
    def interact(self, banner=None, exitmsg=None):
        """Run an enhanced interactive interpreter session."""
        try:
            while True:
                try:
                    line = self.get_input()
                    if line.strip().lower() == "exit":
                        break
                    result = self.runsource(line)
                except KeyboardInterrupt:
                    print("\nKeyboardInterrupt")
        except EOFError:
            pass
        if exitmsg:
            print(exitmsg)

# Create and run the enhanced interactive console
console = EnhancedInteractiveConsole()
console.interact("Interactive Console (type 'exit' to quit)")

