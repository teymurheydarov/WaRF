#include <iostream>
#include <string>

struct Node {
    int value;
    Node* next;
    Node(int v) : value(v), next(nullptr) {}
};

class LinkedList {
public:
    Node* head = nullptr;

    void push(int v) {
        Node* n = new Node(v);
        n->next = head;
        head = n;
    }

    // Removes and returns the front value — caller owns nothing
    int pop() {
        if (!head) return -1;
        Node* old = head;
        head = head->next;
        int val = old->value;
        delete old;
        return val;
    }

    // Returns a pointer to the front node — dangling after pop()
    Node* front() {
        return head;
    }

    // Frees all nodes
    void clear() {
        while (head) {
            Node* tmp = head->next;
            delete head;
            head = tmp;
        }
    }

    ~LinkedList() {
        clear();
    }
};

void demonstrate_uaf() {
    LinkedList list;
    list.push(1);
    list.push(2);

    Node* ref = list.front();   // pointer to node 2
    list.pop();                 // deletes node 2 — ref is now dangling
    std::cout << ref->value;    // use-after-free
}

void demonstrate_double_free() {
    Node* n = new Node(42);
    delete n;
    delete n;                   // double-free — undefined behaviour
}
